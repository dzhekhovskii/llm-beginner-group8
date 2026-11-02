# 0004: Score with exact match and a rule where possible, and with a Sonnet 5.5 judge we calibrated and swapped

- **Status:** accepted
- **Date:** 2026-11-02
- **Author:** Hadiqa Javaid
- **Lesson:** L04

## Context

We must say how often the component is right, on 30 cases written and checked by the group. Lesson 4 showed
the traps: BLEU gave a wrong answer 79 and a right one 4 (it rewards copying the reference's words); exact match
missed 14 to 16 right short answers per variant ("€4,90" against "4,90 €"); judges changed their verdict with
the order on 5 (Sonnet 5.5) to 11 (qwen2.5:3b) pairs of 25.

## Options considered

| Option | For | Against |
|---|---|---|
| Exact match / token F1 on `short_answer` | No model, cheap, reproducible | Misses right answers worded differently; useless on full sentences |
| BLEU, ROUGE-L | Standard, no model | Reward copying words: a wrong number scores high |
| Judge: the component's own model (Haiku 5.5) | Cheapest | Grades its own model's work |
| **Judge: Claude Sonnet 5.5** | A different, stronger model; fewest order flips in lesson 4 (5/25) | Same vendor: a weaker control than another vendor; about 17 times the component's cost per call as measured (20 times per token at list prices) |
| Rule in code for unanswerable cases | No model, exact | Only for those cases |

## Criteria

Can we trust it (agreement with our own scores), does it score meaning rather than words, what does it cost.

## Decision

- Unanswerable cases: right when `answerable` is false, a rule in code.
- Answerable cases: the judge, `claude-sonnet-5-5`, scores the sent answer on the four criteria of
  `evals/rubric.md` (correct, complete, grounded, clear), as a record; a case is right when "correct" is 4 or 5.
  Length earns nothing. We did not use a judge from another vendor: our keys and `src/llm.py` are set up for Claude
  models only, and qwen2.5:3b changed its verdict with the order more often than Sonnet 5.5 in lesson 4 (11 pairs of
  25 against 5). The cost is that judge and component share a vendor, so they may share blind spots.
- Exact match and token F1 on the short answer, with our tested normalisation, reported next to it; BLEU and
  ROUGE-L recorded, never used to decide.
- The judge is calibrated against ten answers scored by hand, and comparisons between strategies are judged in both
  orders: a verdict that changes with the order is not counted. The results are in `docs/evaluation.md`.

## Consequences

Each answerable test case costs a judge call on top of the component's own, and a disagreement between the judge and us is read
case by case (both in `docs/evaluation.md`). To watch: a judge we have not calibrated again after a prompt change is
an instrument we no longer know.
