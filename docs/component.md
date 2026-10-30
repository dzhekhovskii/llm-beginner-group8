
## The task

Albert's Marketplace's customers ask, every day, questions whose answer is a rule of the company: how many
days they have to return an item, whether an opened product can be returned, what delivery costs, whether
they can pay by bank transfer. The answers exist in the company's help centre, but nobody reads six PDFs to
find them, and a general-purpose model answers anyway, fluently and wrongly: asked without the help centre,
Claude Haiku 4.5 said returns are accepted for "typically 30 days" in 3 runs out of 3, while the policy is
21 days, and that returns are "typically free", while they cost €3.95.

Our component is the help centre's assistant: the customer asks a question in their own words and language,
and gets a short answer taken only from the help centre, with its sources, or "the help centre does not say"
when it is silent. Support agents receive the questions the component could not answer.

## Which component

**A retrieval layer (RAG).** The answer to each question already exists in the company's documents and must
come from them, not from the model's general knowledge, so the model must read the right passages before it
answers. A classifier does not fit: the output is an answer, not a label from a fixed list. An extraction
tool does not fit either: we are not turning texts into records, we are answering questions from a body of
documents. RAG also keeps answers current: when a policy changes, we replace the document, not the model.
See `docs/decisions/0001-component-and-task.md`.

## Inputs and outputs

| | |
|---|---|
| Input | One customer question, in natural language, in any of the six countries' languages |
| Output | What is sent to the customer: an answer in one to three sentences, in the question's language, taken only from the retrieved passages; or "the help centre does not cover it"; or a safe fallback when the output check blocks the answer. Internally, a checked record: `answer`, `short_answer`, `answerable`, `citations` (`src/schema.py`) |
| Data used | Albert's Marketplace help centre, release `policy-corpus-v1.0.0` (6 PDFs, each checked against the release's SHA-256 `CHECKSUMS`), with the product pages replaced by the copy one seller edited (course labs, `l03-rag/data/05-product-pages-injected.pdf`, SHA-256 `4cd2b1ee…69d1`). Test file: `evals/test_cases.csv` (30 cases) |

## How it works

```
question ──► embed (multilingual-e5-small) ──► FAISS: the 3 nearest passages
                                                       │
            help-centre passages ──► <help_centre>     │  our code chooses the field from the id
            seller passages ──sanitised──► <seller_pages>
                                                       ▼
              system prompt (prompts/answer_<strategy>.md) + the question as the user message
                                                       │
                     src/llm.py: structured output, stop_reason checked, our rules validated,
                     re-prompted at most twice, every call logged to runs/calls.csv
                                                       ▼
                     output check: no contact the company does not publish ──► SENT
```

## Strategies compared

Zero-shot, few-shot and chain-of-thought on the same 30 test cases (L04). Full table, Pareto front and limits
in `docs/evaluation.md`.

| Strategy | Right, of 30 | Cost per 1,000 calls | Median latency | Prompt file |
|---|---|---|---|---|
| Zero-shot | [from the report] | [ ] | [ ] | `prompts/answer_zero_shot.md` |
| Few-shot | [ ] | [ ] | [ ] | `prompts/answer_few_shot.md` |
| Chain-of-thought | [ ] | [ ] | [ ] | `prompts/answer_cot.md` |

Model `claude-haiku-5-5`, run on [YYYY-MM-DD], default parameters (temperature not set), k = 3 passages,
max_tokens 4,000, test file `evals/test_cases.csv` (30 cases). A case is right when the judge
(`claude-sonnet-5-5`) scores it 4 or 5 on "correct" (`evals/rubric.md`); an unanswerable case is right when the
component says it cannot answer.

## Deployment recommendation

[Two sentences, from `docs/evaluation.md`: the strategy and the model we would deploy, the numbers it rests on,
what it still gets wrong, and what would make us change our mind.]
