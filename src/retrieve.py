"""Retrieval: the help centre, cut into passages, embedded, indexed, searched.

    from src.retrieve import HelpCentre
    centre = HelpCentre()                      # downloads and checks the PDFs once, builds the index (~1 min)
    passages = centre.retrieve("Can I pay by bank transfer?")   # the 3 nearest, each {"id", "text", "score"}

The documents (see data/README.md):
  - Albert's Marketplace's release policy-corpus-v1.0.0, every PDF checked against the release's CHECKSUMS;
  - in place of 05-product-pages.pdf, the copy one seller edited (from the course labs, checksum fixed below),
    so the component is built and tested against the injection it will meet.

Choices (docs/decisions/0003-retrieval.md):
  - embedding model intfloat/multilingual-e5-small: multilingual (customers write in 6 countries), runs locally
    (no key, no cost, no customer text sent anywhere to be embedded), reads at most 512 tokens;
  - passages of whole sentences, packed up to CHUNK_TOKENS tokens counted with THE MODEL'S OWN tokenizer,
    and the code refuses to build an index with a passage longer than the model reads (it would be cut silently);
  - exact search (FAISS IndexFlatIP on normalised vectors = cosine): 37 passages need nothing approximate;
  - the K=3 nearest passages.
"""

import hashlib
import re
import urllib.request
from pathlib import Path

import faiss
import numpy as np
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "data" / "policy-corpus"

RELEASE = ("https://github.com/TangoAI-AlbertSchool-Data-Eng-Cloud/albert-marketplace"
           "/releases/download/policy-corpus-v1.0.0/")
INJECTED_URL = ("https://raw.githubusercontent.com/TangoAI-AlbertSchool-Data-Eng-Cloud/llm-course-labs/main/"
                "l03-rag/data/05-product-pages-injected.pdf")
INJECTED_SHA256 = "4cd2b1ee432762d74c08b47454a8a04d8ef56c7f760b19788c1011ff1aec69d1"

EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
CHUNK_TOKENS = 500
K = 3

# Passages written by people outside the company's control: the sellers' product pages and the catalogue.
UNTRUSTED_PREFIXES = ("05-", "06-")


def is_untrusted(passage_id):
    return passage_id.startswith(UNTRUSTED_PREFIXES)


def _fetch(url, path, sha256=None):
    """Make sure the file is on disk and is the right one: a file that differs by one byte is refused."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    if sha256 and hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        path.unlink()
        raise RuntimeError(f"{path.name}: checksum mismatch, file deleted. Run again to download it.")
    return path


def fetch_corpus():
    """Download the help centre once into data/policy-corpus/, checked. Returns the list of PDF paths used."""
    sums = _fetch(RELEASE + "CHECKSUMS", CORPUS_DIR / "CHECKSUMS").read_text().splitlines()
    sums = dict(reversed(line.split()) for line in sums if line.strip())
    files = [_fetch(RELEASE + name, CORPUS_DIR / name, digest) for name, digest in sorted(sums.items())
             if name.endswith(".pdf") and not name.startswith("05-")]
    files.append(_fetch(INJECTED_URL, CORPUS_DIR / "05-product-pages-injected.pdf", INJECTED_SHA256))
    return sorted(files)


def normalise_space(s):
    return re.sub(r"\s+", " ", s).strip()


def load_pdf(path):
    """The text of every page, joined; pypdf's line breaks inside a sentence are removed."""
    text = "\n".join(p.extract_text() for p in PdfReader(path).pages)
    return re.sub(r"(?<!\n)\n(?!\n)", " ", text)


class HelpCentre:
    """The documents, their passages and the index."""

    def __init__(self, chunk_tokens=CHUNK_TOKENS, model_name=EMBEDDING_MODEL):
        from sentence_transformers import SentenceTransformer   # slow to import: only when an index is built
        self.model = SentenceTransformer(model_name)
        self.chunk_tokens = chunk_tokens
        if chunk_tokens > self.model.max_seq_length:
            raise ValueError(f"chunks of {chunk_tokens} tokens, but {model_name} reads only "
                             f"{self.model.max_seq_length}: the end of each passage would be ignored silently")
        files = fetch_corpus()
        self.docs = {f.stem.replace("-injected", ""): load_pdf(f) for f in files}
        self.passages = [p for name, text in self.docs.items() for p in self.chunk(name, text)]
        longest = max(self.n_tokens("passage: " + p["text"]) for p in self.passages)
        assert longest <= self.model.max_seq_length, f"a passage of {longest} tokens would be cut"
        vectors = self.model.encode(["passage: " + p["text"] for p in self.passages], normalize_embeddings=True)
        self.index = faiss.IndexFlatIP(vectors.shape[1])
        self.index.add(np.asarray(vectors, dtype="float32"))
        self.by_id = {p["id"]: p for p in self.passages}

    def n_tokens(self, text):
        return len(self.model.tokenizer(text, add_special_tokens=False)["input_ids"])

    def chunk(self, name, text):
        """Whole sentences, packed up to chunk_tokens (minus room for the "passage: " prefix and special tokens)."""
        budget = self.chunk_tokens - 8
        sentences = re.split(r"(?<=[.!?:])\s+(?=[A-Z0-9\"(])", text)
        out, cur, n = [], [], 0
        for s in sentences:
            k = self.n_tokens(s)
            if cur and n + k > budget:
                out.append(" ".join(cur))
                cur, n = [], 0
            cur.append(s)
            n += k
        if cur:
            out.append(" ".join(cur))
        return [{"id": f"{name}#{i}", "text": t} for i, t in enumerate(out)]

    def retrieve(self, question, k=K):
        """The k passages nearest to the question, best first, each with its cosine score."""
        q = self.model.encode(["query: " + question], normalize_embeddings=True)
        scores, ids = self.index.search(np.asarray(q, dtype="float32"), k)
        return [{**self.passages[i], "score": float(s)} for s, i in zip(scores[0], ids[0])]

    def stats(self):
        """For the decision record: how many passages, and their sizes in the model's tokens."""
        sizes = [self.n_tokens("passage: " + p["text"]) for p in self.passages]
        return {"passages": len(sizes), "max_tokens": max(sizes), "median_tokens": sorted(sizes)[len(sizes) // 2],
                "model": EMBEDDING_MODEL, "model_max_seq_length": self.model.max_seq_length}


def has_evidence(evidence, passages):
    """Was the evidence sentence (from the test case) among the passages retrieved? True when there is none."""
    if not evidence:
        return True
    ev = normalise_space(evidence)
    return any(ev in normalise_space(p["text"]) for p in passages)


if __name__ == "__main__":
    import sys
    centre = HelpCentre()
    print(centre.stats())
    for p in centre.retrieve(" ".join(sys.argv[1:]) or "How many days do I have to return an item?"):
        print(f"{p['score']:.3f}  {p['id']}  {p['text'][:90]}...")
