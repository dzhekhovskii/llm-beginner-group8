# 0002: Structured outputs, our rules validated in code, and the SDK as the only retry layer

- **Status:** accepted
- **Date:** 2026-10-31
- **Author:** Naye Kanoute
- **Lesson:** L02

## Context

The rest of our code needs each answer as a record it can load: `answer`, `short_answer`, `answerable`,
`citations`. Lesson 2 measured three routes on Claude Haiku 4.5 (20 reviews, 2 October 2026): JSON asked for in
the prompt loaded 0/60 times as returned (wrapped in a code fence); a strict tool 20/20 (+1,031 input tokens per
call); structured outputs 60/60 (+728 input tokens). The API guarantees the shape, not the content: a valid
record can still cite a passage that was never retrieved (lesson 3: 2 runs of 3 cited `02-delivery#5`, which
does not exist).

Retries: the SDK already retries transient errors twice by default. Stacking tenacity on top turned one
overloaded call into 9 requests, and re-sent a permanent 400 three times (lesson 2).

## Options considered

| Option | For | Against |
|---|---|---|
| JSON asked for in the prompt | No extra input tokens | 0/60 loadable as returned in lesson 2 |
| A strict tool | Valid 20/20 | The most input tokens (Anthropic's tool system prompt) |
| **Structured outputs + validation in our code** | Shape guaranteed; our rules checked against what we retrieved; the error re-sent to the model | Adds input tokens; `parse()` cannot be used for our rules (it loses the text to re-prompt with) |
| Retries: SDK + tenacity | More control over the policy | Two layers multiply: 9 requests for one call |
| **Retries: the SDK only** (`max_retries=4`) | Transient errors only (connection, timeout, 408, 409, 429, 5xx), backoff with jitter; permanent errors raised at once | Its policy is the SDK's, not ours to tune finely |

## Criteria

Loadable answers, rules a JSON schema cannot express, bounded cost when the model cannot meet a rule, one retry
policy we can explain.

## Decision

Two kinds of failure, two separate mechanisms, each with a hard limit: transport errors (network, rate limits,
server errors) are retried by the SDK only; content errors (an answer that breaks one of our rules) are
re-prompted at most twice.

`messages.create` with `output_config.format` (a JSON schema from `anthropic.transform_schema`), then
`model_validate_json` with our validators and the retrieved ids as context (`src/schema.py`); on a validation
error, the model's answer and the error are sent back, **at most twice**, then the call gives up and the
customer gets a fallback. `stop_reason` is checked first: `max_tokens` or `refusal` is a failure, never parsed.
Everything goes through one function, `src/llm.py: structured_call`, which logs every call to `runs/calls.csv`.

## Consequences

To be filled after the evaluation run (`runs/calls.csv`, 30 cases): [x] answers valid at the first attempt,
[x] after one re-prompt, [x] after two, [x] given up; each re-prompt cost a whole call. Input tokens per call:
[median], of which the schema adds about [x] (compare with a plain call). To watch: a rule the model keeps
breaking costs three calls; the cap is what bounds it.
