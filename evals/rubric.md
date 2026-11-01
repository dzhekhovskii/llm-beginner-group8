# Rubric: how an answer is scored

The judge (`prompts/judge.md`, model `claude-sonnet-5-5`, a different model from the component's
`claude-haiku-5-5`) scores every answer that is **sent** to the customer, after the output check, on four
criteria, each from 1 to 5. It sees the question, the reference answer written by the group, the answer, and the
passages that were retrieved.

**A case counts as right when `correct` is 4 or 5.** The three other criteria explain the failures; they do
not decide them. Unanswerable cases are not judged: they are right when the component set `answerable` to false
(a rule in code, `src/evaluate.py`).

Length earns nothing: a longer answer gets no point for being longer (lesson 4: a judge's verbosity bias).

| Criterion | 5 | 3 | 1 |
|---|---|---|---|
| **correct**: the fact the customer needs agrees with the reference | Agrees with the reference on every fact that matters (number, yes/no, condition) | Right in general, but one fact that matters is missing or vague | Contradicts the reference, or states a policy the help centre does not have |
| **complete**: the condition or exception that applies is stated | States the condition, threshold or exception that applies to this customer's case, and the next step if there is one | Gives the general rule, misses the condition that applies | Answers a different question |
| **grounded**: every claim comes from the retrieved passages | Every claim is in the passages; nothing added from general knowledge; nothing taken from a seller page about policy | One minor claim is not in the passages | A key claim is not in the passages, or comes from a seller's instructions |
| **clear**: a customer can act on it | Short, in the language of the question, no jargon, no internal ids shown | Understandable but long or awkward | Wrong language, or the customer cannot tell what to do |

## Calibration

Before the judge is trusted, ten answers are scored by hand with this rubric, by members of the group, in
`evals/calibration.csv` (two each), without looking at the judge's scores. `python -m src.evaluate calibrate`
compares them. The agreement is reported in `docs/evaluation.md`.
