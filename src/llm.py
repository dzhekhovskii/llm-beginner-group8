"""The ONE place in this repository that calls the API.

Every call the component, the judge and the tests make goes through structured_call(). It:

  1. asks for an answer in the schema's shape (structured outputs: output_config.format, a JSON schema
     built from the Pydantic model with anthropic.transform_schema);
  2. checks stop_reason before trusting the text: "max_tokens" (cut off) or "refusal" -> a clear failure;
  3. validates the text with the model's own rules (schema.py), in our code, with a context;
  4. on a validation error, re-prompts with the error message, AT MOST twice, then gives up with a Failure
     instead of returning a record;
  5. appends one row per API call to runs/calls.csv: time, model, tokens, attempt, valid, cost, latency.

Retries: ONE layer, the SDK's. The client retries transient errors only (lost connections, timeouts, 408,
409, 429 honouring retry-after, 5xx), with exponential backoff and jitter. A permanent error (400, 401,
403, 404, 413) is raised at once: sending it again would fail the same way. No tenacity on top: two layers
multiply (lesson 2: 9 requests for one overloaded call).

Why messages.create and not messages.parse(): parse() validates inside the SDK, so when one of our rules
fails the tokens are billed and the text is lost, with nothing to re-prompt with (lesson 2, slide 29).

The key: read from .env by python-dotenv (ANTHROPIC_API_KEY, or ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN
for OpenRouter). The client is created without a key argument: no key ever appears in this code.
"""

import csv
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CALLS_LOG = ROOT / "runs" / "calls.csv"

# The model our component uses, and the judge: a different model (lesson 4: a judge must not grade its own model).
COMPONENT_MODEL = "claude-haiku-5-5"
JUDGE_MODEL = "claude-sonnet-5-5"

# $ per million tokens (input, output). Anthropic's pricing page, as checked by the course on 14 October 2026;
# Haiku 5.5 and Sonnet 5.5 re-checked by the group on 2 November 2026, unchanged.
# Re-check them on the day of the run, and write the date in docs/evaluation.md.
PRICE = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}
CACHE_WRITE = 1.25                       # a 5-minute cache write costs 1.25 x the input price
CACHE_READ = {"claude-sonnet-5-5": 0.05}  # a cache read: 0.1 x the input price, 0.05 on Sonnet 5.5

MAX_REPROMPTS = 2       # after the first answer, at most two corrections, then give up
SDK_MAX_RETRIES = 4     # the SDK's retry layer, on transient errors only

LOG_FIELDS = ["timestamp", "tag", "model", "attempt", "input_tokens", "output_tokens",
              "cache_write_tokens", "cache_read_tokens", "stop_reason", "valid", "error",
              "ms", "cost_usd", "request_id"]

_client = None


def get_client():
    """The shared client, created once. max_retries: the SDK is our only retry layer."""
    global _client
    if _client is None:
        load_dotenv(ROOT / ".env")
        _client = anthropic.Anthropic(max_retries=SDK_MAX_RETRIES)
    return _client


def cost(model, usage, count_output=True):
    """The price of one call in dollars, from its usage: input and output at their own prices, plus cache."""
    if usage is None:
        return 0.0
    p_in, p_out = PRICE[model]
    tokens_in = getattr(usage, "input_tokens", 0) or 0
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    tokens_out = (getattr(usage, "output_tokens", 0) or 0) if count_output else 0
    return (tokens_in * p_in + written * p_in * CACHE_WRITE
            + read * p_in * CACHE_READ.get(model, 0.10) + tokens_out * p_out) / 1_000_000


def _log(row):
    """Append one row to runs/calls.csv, with a header if the file is new."""
    CALLS_LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not CALLS_LOG.exists()
    with CALLS_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


@dataclass
class Result:
    """What structured_call returns. record is None when the call gave up (then failure says why)."""
    record: BaseModel | None
    attempts: list = field(default_factory=list)   # one dict per API call: tokens, error, ms, cost
    failure: str | None = None

    @property
    def ok(self):
        return self.record is not None

    @property
    def cost_usd(self):
        return sum(a["cost_usd"] for a in self.attempts)

    @property
    def ms(self):
        return sum(a["ms"] for a in self.attempts)

    @property
    def reprompts(self):
        return max(0, len(self.attempts) - 1)


def structured_call(*, model, system, user, schema, context=None, max_tokens=4000, tag="", client=None, log=True):
    """One question, answered as a checked record of `schema`, or a Failure after two re-prompts.

    model    the model id;  system  the system prompt (rules + passages);  user  the user message
    schema   a Pydantic model class (schema.Answer, schema.AnswerCoT, schema.Verdict, ...)
    context  passed to the validators, e.g. {"retrieved_ids": {...}}
    tag      written in runs/calls.csv to say what the call was for, e.g. "few_shot:C07" or "judge:C07"
    """
    client = client or get_client()
    json_schema = anthropic.transform_schema(schema)
    messages = [{"role": "user", "content": user}]
    result = Result(record=None)

    for attempt in range(1, MAX_REPROMPTS + 2):
        t0 = time.perf_counter()
        r = client.messages.create(
            model=model, max_tokens=max_tokens, system=system, messages=messages,
            output_config={"format": {"type": "json_schema", "schema": json_schema}},
        )
        ms = round((time.perf_counter() - t0) * 1000)
        # Some models think first: the record is in the text blocks, never in a thinking block.
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tag": tag, "model": model, "attempt": attempt,
            "input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens,
            "cache_write_tokens": getattr(r.usage, "cache_creation_input_tokens", 0) or 0,
            "cache_read_tokens": getattr(r.usage, "cache_read_input_tokens", 0) or 0,
            "stop_reason": r.stop_reason, "valid": False, "error": "", "ms": ms,
            "cost_usd": round(cost(model, r.usage), 8), "request_id": getattr(r, "_request_id", "") or "",
        }

        # stop_reason first: a cut-off or a refusal may not match the schema, and an error message will not fix it.
        if r.stop_reason in ("max_tokens", "refusal"):
            row["error"] = f"stop_reason={r.stop_reason}"
            result.attempts.append(row)
            if log:
                _log(row)
            result.failure = row["error"]
            return result

        try:
            record = schema.model_validate_json(text, context=context or {})
        except ValidationError as e:
            error = "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
            row["error"] = error
            result.attempts.append(row)
            if log:
                _log(row)
            # Re-prompt: the model's own answer, then what was wrong with it.
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"Your record breaks these rules: {error}. Send the corrected record."},
            ]
            continue

        row["valid"] = True
        result.attempts.append(row)
        if log:
            _log(row)
        result.record = record
        return result

    result.failure = f"gave up after {MAX_REPROMPTS} re-prompts: {result.attempts[-1]['error']}"
    return result
