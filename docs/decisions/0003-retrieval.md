# 0003: Retrieve the 3 nearest passages of whole sentences, up to 500 tokens, with multilingual-e5-small

- **Status:** accepted
- **Date:** [YYYY-MM-DD]
- **Author:** Alzira Ferreira
- **Lesson:** L03

## Context

Our component needs facts no model has read: this company's return window, fees and rules. We checked it on
three of our test cases run through `src/llm.py` with no passage at all: [Cxx, Cxx, Cxx: what the model
answered, and what the help centre says]. It invented a policy, so the component needs retrieval.

The help centre: 6 PDFs, release `policy-corpus-v1.0.0`, every file checked against the release's SHA-256
`CHECKSUMS` (`src/retrieve.py: fetch_corpus`). Customers write in French, German, Spanish, Italian, Dutch and
English; the documents are in English.

## Options considered

| Option | For | Against |
|---|---|---|
| The whole help centre in every prompt | Nothing to retrieve, nothing missed | About 19,000 tokens per question; does not scale to 150 catalogue products and beyond |
| `all-MiniLM-L6-v2` | Small, fast | English only: a French question scored 0.14 against its English twin (lesson 3) |
| `paraphrase-multilingual-MiniLM-L12-v2` | Multilingual | Reads 128 tokens: 36 of 37 chunks cut silently, evidence found for 7/12 questions (lesson 3) |
| **`multilingual-e5-small`** | Multilingual (0.95 on the French twin); reads 512 tokens; evidence found for 12/12 (lesson 3); local, free, no customer text sent out | Scores sit between 0.7 and 1.0: only their order means something; needs the `query:` / `passage:` prefixes |
| Fixed 500-token windows | Simple | 9 of 39 chunks start mid-word (lesson 3) |
| **Whole sentences, packed up to 500 tokens** | No chunk starts mid-word; every chunk within the model's 512-token limit, checked in code | A rule can still be separated from its exception (the opened-products rule) |

## Criteria

Evidence retrieved in the top 3 (measured on our cases: `evidence_retrieved` in `runs/results_*.csv`),
languages, cost, no silent truncation.

## Decision

`intfloat/multilingual-e5-small`, chunks of whole sentences up to 500 tokens counted with the model's own
tokenizer (`max_seq_length` = 512, and `HelpCentre` refuses to build an index with a longer passage), exact
search (`faiss.IndexFlatIP` on normalised vectors = cosine), k = 3.

On our 30 cases ([date]): the index holds [x] passages, longest [x] tokens; the evidence was in the top 3 for
**[x]/28** answerable cases. Misses: [Cxx: what was retrieved instead, and why, e.g. a seller question that
retrieved returns passages].

## Consequences

- The answer is only as good as the 3 passages: a miss is a wrong answer however good the prompt (see the
  failure modes in `docs/evaluation.md`).
- A document can go out of date: the release version is in the README; a new policy means a new release and a
  rebuilt index.
- To try next: k = 5 for seller questions, or the whole help centre with prompt caching (lesson 4 measured it at
  about Haiku 4.5's price).
