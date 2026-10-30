
## Context

Albert's Marketplace's customers ask questions whose answer is a company rule: return window, return cost,
delivery cost, payment methods, what happens to their data. The rules are in the help centre (6 PDFs, release
`policy-corpus-v1.0.0`, about 16,500 tokens). A model asked without them invents a plausible policy: Claude
Haiku 4.5 answered "typically 30 days" for returns in 3 runs out of 3 (the policy is 21 days) and "typically
free" (it is €3.95).

The course offered three components: a ticket classifier, a review extractor, a retrieval layer.

## Options considered

| Option | For | Against |
|---|---|---|
| Ticket classifier | Simple to score (exact match on a label); 120 labelled tickets exist | The task we chose has no fixed label set; a classifier would not answer anybody |
| Review extractor | Records are easy to check field by field | Does not answer customers; the product team's need, not the support desk's |
| **Retrieval layer (RAG)** | The answers exist in the documents and must come from them; answers stay current when a document changes; citations can be checked | More moving parts (chunking, embeddings, index); new risks: wrong passage, injected documents |

## Criteria

1. Does it solve the task (a sourced answer to a customer's policy question)? Only RAG does.
2. Can we prove it is right? Yes: each test case holds the help centre's sentence that answers it, so we score
   retrieval and the answer separately.
3. Does it give the course's later steps something to measure? Retrieval (lesson 3), a judge on free text and
   injection through retrieved documents (lesson 4) all apply.

## Decision

A retrieval layer that answers Albert's Marketplace's customers only from the help centre, cites the passages
it used, and says when the help centre is silent.

## Consequences

- Easier: answers are grounded and checkable; a policy change is a new document, not a new prompt.
- Harder: an answer can only be as good as the passage retrieved, and a seller's product page is a document
  anyone can write: we must treat it as untrusted (0005).
- To watch: questions the help centre does not answer (phone number, gift wrapping, loyalty points) must get
  "I don't know", not an invented answer.
