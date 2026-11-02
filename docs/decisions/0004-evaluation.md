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
  Length earns nothing.
- Exact match and token F1 on the short answer, with our tested normalisation, reported next to it; BLEU and
  ROUGE-L recorded, never used to decide.
- Calibration: ten answers scored by hand before reading the judge's scores. Agreement: **10/10**
  (`runs/calibration_summary.md`). Two of the ten (C25, C06) were not scored blind, because the scorer had already
  read the failure review; without them, 8/8. Nine of the ten answers were right, so only C13 tests whether the judge
  catches a wrong answer.
- Comparisons between strategies judged in both orders: 7 of 28 verdicts changed with the order and were not
  counted (`runs/swap_zero_shot_vs_cot.csv`).

## Consequences

The judge cost $0.758 for the whole evaluation ($0.575 to score the three runs, $0.183 for the swap), on top of the
component's $0.037. A disagreement between the judge and us is read case by case: there were none on right/wrong, and
the largest gap on any criterion was one point (for example "clear" on C13: ours 4, the judge's 3). As lesson 4 warned, exact match missed right
answers (22 to 24 of 28 per strategy here), and the judge changed with the order on 7 of 28 pairs, against 5 of 25 in
lesson 4. To watch: a judge we have not calibrated again after a prompt change is an instrument we no longer know.
