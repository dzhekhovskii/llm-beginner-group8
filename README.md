# Albert's Marketplace LLM component: group repo

This repository is your group's LLM component for **Albert's Marketplace**, the
fictional European beauty marketplace of the LLM Fundamentals, Prompting & API
Integration course (MSA-DATI07-08, Albert School).

> **Our component:** a retrieval layer (RAG). The help centre's assistant for Albert's Marketplace's customers answers their policy questions only from the company's help centre, with its sources, or says the help centre does not cover it. Jump to [What the component does](#what-the-component-does), [Install](#install), [Run the evaluation](#run-the-evaluation) and [Run the tests](#run-the-tests). Results: `docs/evaluation.md`. Defence slides: `docs/defence/`.

It starts almost empty. Every lesson adds a layer on top of the previous one. By
the end of the course it holds the component your group defends orally: one of
- a prompt-driven **classifier** (support tickets)
- a **structured-extraction** tool (product reviews)
- a **retrieval** layer that answers from the company's own documents

with reproducible code, a comparison of prompting strategies on 30 test cases,
an evaluation report, prompt-injection guardrails and a cost per 1,000 calls.

## Team

| Name | GitHub | Role |
|---|---|---|
|Nicolas Dollet|ndollet-sudo|Guardrails and injection tests (decision 0005)|
|Naye Kanoute|nayekanoute|API call, structured output and retries, `src/llm.py` (decision 0002)|
|Alzira Ferreira|Icetrucklr|Retrieval, `src/retrieve.py` (decision 0003)|
|Hadiqa Javaid|HadiqaJ94|Evaluation, judge and calibration (decision 0004)|
|Danila Zhekhovskii|dzhekhovskii|Component, prompts and recommendation (decision 0001)|

## How this repo grows

| Lesson | What your group adds | Where |
|---|---|---|
| L01 · Tokens and prompting | The business task your component serves, a first prompt, its first 10 test cases | `docs/component.md`, `prompts/`, `evals/` |
| L02 · API and structured outputs | Calls through the API with retries and validated output; how keys are handled | `src/`, `requirements.txt` |
| L03 · Retrieval-augmented generation | Retrieval, if your task needs it, **or a decision record saying why not** | `src/`, `docs/decisions/` |
| L04 · Evaluation, cost and guardrails | The evaluation report: golden set, rubric, 30 cases × 3 strategies, failure modes, cost per 1,000 calls, an injection test that must refuse | `evals/`, `docs/` |
| L05 · Review | Project clinic: what the defence will ask | |
| L06 · Project defences | The deployment recommendation you defend | `docs/component.md` |

Starter files for later lessons arrive as **pull requests** opened by the
teaching team. Review and merge them like any other change.

## How we work

- **Every change goes through a pull request,** reviewed by another member
  before it reaches `main`.
- **One decision, one record** in `docs/decisions/`: a prompt pattern, a model,
  a schema, a retrieval setting. Every member writes at least one. At the oral
  defence, each of you defends a choice unprepared.
- **The commit history is graded.** Commit in small steps, with messages that
  say why.
- **A prompt is code.** It lives in `prompts/`, under version control, and a
  change to it is measured on the test cases before it is merged.
- **Every figure says where it came from:** the model, the date, the
  parameters and the test file. A model does not give the same answer twice.

## Your API key

**Each of you has your own key, with a spending limit:** an Anthropic key
(`sk-ant-…`) or an OpenRouter key (`sk-or-…`), which reaches the same Claude
models. It is personal: it never goes in this repository, in a notebook, in a
screenshot or in a chat message.

- Keep it in a `.env` file, which `.gitignore` already excludes. Copy
  `.env.example` to `.env` and uncomment the lines for your kind of key: one
  line for an Anthropic key, two for an OpenRouter key. The code is the same
  for both.
- **If a key reaches GitHub, even for a minute, tell the teaching team at once**
  so it can be revoked. Deleting the commit does not help: the key has already
  been copied.

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

## Ownership

**No licence is granted for this repository.**
- **The template:** this README, the `docs/` templates and the folder structure
  remain the course author's intellectual property. Do not reuse them outside
  the course.
- **Your work:** what your group writes here belongs to your group.



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

On an Intel Mac, the pinned torch version has no build: the injection tests were run there with torch 2.2.2, transformers 4.44.2 and sentence-transformers 3.4.1 (see `docs/decisions/0005-guardrails.md`).

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
