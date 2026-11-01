## What the component does

The help centre's assistant for Albert's Marketplace's customers: a question in, a short answer out, taken only
from the company's help centre, with the passages it used, or "the help centre does not cover it". Details:
`docs/component.md`. Results: `docs/evaluation.md`.

## Install

Python 3.12, in a virtual environment, from the repository's root:

```bash
pip install -r requirements.txt
cp .env.example .env        # then uncomment your key's lines in .env (see "Your API key")
```

The first run downloads the help centre (release `policy-corpus-v1.0.0`, every file checked against its
SHA-256) into `data/policy-corpus/` and the embedding model `intfloat/multilingual-e5-small` (about 470 MB).
Both are ignored by Git.

## Run it on one question

```bash
python -m src.assistant "How many days do I have to return an item?"
python -m src.assistant "Puis-je payer en espèces ?" --strategy cot
python -m src.assistant "How many days do I have to return an item?" --closed-book   # no retrieval
```

## Run the evaluation

```bash
python -m src.evaluate run --strategy zero_shot     # 30 cases + the judge: about $0.25
python -m src.evaluate run --strategy few_shot
python -m src.evaluate run --strategy cot
python -m src.evaluate swap --a zero_shot --b cot
python -m src.evaluate calibrate                    # needs evals/calibration.csv filled in by hand
python -m src.evaluate report                       # writes the table into docs/evaluation.md
```

Every API call is logged to `runs/calls.csv` (tokens, cost, latency, attempt, valid). Commit `runs/`.

## Run the tests

```bash
pytest tests/test_llm.py tests/test_evaluate.py tests/test_guardrails_offline.py   # no key, no download
pytest tests/test_guardrails.py     # the injection attacks, 5 runs each: needs your key (under $0.05)
```

## Data

| Document | Source | Version | Checked by |
|---|---|---|---|
| Help centre, 5 PDFs (`01-` to `04-`, `06-`) | Albert's Marketplace release | `policy-corpus-v1.0.0` (1 September 2026 policies) | SHA-256 against the release's `CHECKSUMS` |
| Product pages, as one seller edited them (`05-`) | course labs, `l03-rag/data/05-product-pages-injected.pdf` | 1 October 2026 extract | SHA-256 `4cd2b1ee432762d74c08b47454a8a04d8ef56c7f760b19788c1011ff1aec69d1` |

The policies are fictional, written for the course; CC BY-SA 4.0. A new release means a rebuilt index and a
new evaluation.

## Keys: for a new member

1. Your key goes in `.env`, next to `.env.example`, never anywhere else: not in code, a notebook, a screenshot or a chat.
2. `.env` is listed in `.gitignore`, so Git never sees it; check with `git status` before every commit.
3. Use your own key, never a teammate's: each has its own spending limit.
4. If a key is pushed, even for a minute, tell the school coordinator at once so it can be revoked.
5. Deleting the commit does not help: the key has already been copied.
