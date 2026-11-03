# Albert's Marketplace help-centre assistant: group 8

> **Our component:** a retrieval layer (RAG). The help centre's assistant for Albert's Marketplace's customers answers their policy questions only from the company's help centre, with its sources, or says the help centre does not cover it. Jump to [What the component does](#what-the-component-does), [Install](#install), [Run the evaluation](#run-the-evaluation) and [Run the tests](#run-the-tests). Results: `docs/evaluation.md`. Defence slides: `docs/defence/`.

## What the component does

The help centre's assistant for Albert's Marketplace's customers: a question in, a short answer out, taken only
from the company's help centre, with the passages it used, or "the help centre does not cover it". Details:
`docs/component.md`. Results: `docs/evaluation.md`.

For whom: Albert's Marketplace's customers, who ask policy questions (returns, delivery, payment, their data); support agents receive the questions it cannot answer.

## Team

| Name | GitHub | Role |
|---|---|---|
|Danila Zhekhovskii|dzhekhovskii|Component, prompts and recommendation (decision 0001)|
|Naye Kanoute|nayekanoute|API call, structured output and retries, `src/llm.py` (decision 0002)|
|Alzira Ferreira|Icetrucklr|Retrieval, `src/retrieve.py` (decision 0003)|
|Hadiqa Javaid|HadiqaJ94|Evaluation, judge and calibration (decision 0004)|
|Nicolas Dollet|ndollet-sudo|Guardrails and injection tests (decision 0005)|


## Install

Python 3.12, in a virtual environment, from the repository's root:

```bash
pip install -r requirements.txt
cp .env.example .env        # then uncomment your key's lines in .env (see "Your API key")
```

The first run downloads the help centre (release `policy-corpus-v1.0.0`, every file checked against its
SHA-256) into `data/policy-corpus/` and the embedding model `intfloat/multilingual-e5-small` (about 470 MB).
Both are ignored by Git.

On an Intel Mac, the pinned torch version has no build: the injection tests were run there with torch 2.2.2, transformers 4.44.2 and sentence-transformers 3.4.1 (see `docs/decisions/0005-guardrails.md`).

### Your API key

**Each of you has your own key, with a spending limit:** an Anthropic key
(`sk-ant-…`) or an OpenRouter key (`sk-or-…`), which reaches the same Claude
models. It is personal.

1. Your key goes in `.env`, next to `.env.example`, never anywhere else: not in this repository's code, a notebook, a screenshot or a chat.
   Copy `.env.example` to `.env` and uncomment the lines for your kind of key: one line for an Anthropic key,
   two for an OpenRouter key. The code is the same for both.
2. `.env` is listed in `.gitignore`, so Git never sees it; check with `git status` before every commit.
3. Use your own key, never a teammate's.
4. **If a key reaches GitHub, even for a minute, tell the teaching team at once** so it
   can be revoked. Deleting the commit does not help: the key has already been copied.

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

## Layout

```
docs/
  component.md      the task, the users, the deployment recommendation
  evaluation.md     the evaluation report: table, Pareto front, judge, failures, injection tests
  pareto.png        the Pareto front
  decisions/        one record per decision (0001 to 0005)
  defence/          the defence slides (PDF)
prompts/            every prompt, versioned: the three strategies and the judge
evals/              test cases, rubric, calibration
src/                the code: retrieval, the API call, guardrails, the assistant, the evaluation
tests/              offline tests and the live injection tests
runs/               every result file and the log of every API call (calls.csv)
```

## Data

| Document | Source | Version | Checked by |
|---|---|---|---|
| Help centre, 5 PDFs (`01-` to `04-`, `06-`) | Albert's Marketplace release | `policy-corpus-v1.0.0` (1 September 2026 policies) | SHA-256 against the release's `CHECKSUMS` |
| Product pages, as one seller edited them (`05-`) | course labs, `l03-rag/data/05-product-pages-injected.pdf` | 1 October 2026 extract | SHA-256 `4cd2b1ee432762d74c08b47454a8a04d8ef56c7f760b19788c1011ff1aec69d1` |

The policies are fictional, written for the course; CC BY-SA 4.0. A new release means a rebuilt index and a
new evaluation.

## Ownership

**No licence is granted for this repository.**
- **The template:** this README, the `docs/` templates and the folder structure
  remain the course author's intellectual property. Do not reuse them outside
  the course.
- **Your work:** what your group writes here belongs to your group.
