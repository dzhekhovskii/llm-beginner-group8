# Our component

*Filled in from L01, and kept current: it is the page you present at the defence.*

## The task

Albert's Marketplace holds its operating rules in internal documents (return
and refund policy, seller fees, shipping rules, terms of service, help-centre
articles), and support agents must answer questions from them every
day, such as "How many days does a buyer have to return an opened item?". Today
they search the documents by hand or ask a colleague, which is slow and gives
inconsistent answers, because people quote an outdated version or misremember a
rule. Without the component, a question takes about 5 minutes to answer and
about 25% of answers are wrong or out of date. The result is used by support agents
, who get a sourced answer in seconds.

## Which component

**Retrieval layer (RAG).** The answer to each question already exists in the
company's documents and must come from them, not from the model's general
knowledge. The component retrieves the relevant passages and the model answers
using only those passages, citing the source. A classifier does not fit,
because the output is an answer, not a label from a fixed list. An extraction
tool does not fit either, because we are not turning texts into records, we are
answering questions from a body of documents. RAG also keeps answers current:
when a policy changes, we update the document, not the model.

## Inputs and outputs

| | |
|---|---|
| Input | One question in natural language (a string) |
| Output | An answer based only on the retrieved passages, with the source document and passage ID; or "not found in the documents" when no passage answers the question |
| Data used | `[documents file/folder]`, version [v1 / commit hash], SHA-256 [checksum]; test file `evals/test_cases.csv` |

## Strategies compared

Zero-shot, few-shot and chain-of-thought on the same 30 test cases (L04).

| Strategy | Error rate | Cost per 1,000 calls | Latency | Prompt file |
|---|---|---|---|---|
| Zero-shot | [e.g. 3/10 = 30%] | (L04) | (L04) | `prompts/answer_zero_shot.md` |
| Few-shot | (L04) | (L04) | (L04) | |
| Chain-of-thought | (L04) | (L04) | (L04) | |

First run (L01): model [name and version], date [YYYY-MM-DD], parameters
[temperature=0, max_tokens=..., top_k=... passages], test file
`evals/test_cases.csv` (10 cases). An error is a wrong answer, an answer not
supported by the retrieved passages, or a wrong cited source.

## Deployment recommendation

To be filled in at L04: which variant we would deploy, what it costs, what it
gets wrong, and what would make us change our mind.
