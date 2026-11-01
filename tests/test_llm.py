"""The schema's rules and src/llm.py (re-prompts, stop_reason, log, cost) with a fake client: no key needed.

    pytest tests/test_llm.py
"""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src import llm
from src.schema import Answer, AnswerCoT

RETRIEVED = {"01-returns-and-refunds#0", "02-delivery#0", "05-product-pages#0"}


# --- the schema's rules

def _json(**kw):
    base = {"answer": "You have 21 days.", "short_answer": "21 days", "answerable": True,
            "citations": ["01-returns-and-refunds#0"]}
    base.update(kw)
    return json.dumps(base)


def test_valid_answer_passes():
    a = Answer.model_validate_json(_json(), context={"retrieved_ids": RETRIEVED})
    assert a.citations == ["01-returns-and-refunds#0"]


def test_invented_citation_is_refused_with_an_actionable_message():
    with pytest.raises(ValidationError) as e:
        Answer.model_validate_json(_json(citations=["02-delivery#5"]), context={"retrieved_ids": RETRIEVED})
    assert "02-delivery#5" in str(e.value) and "Cite only these ids" in str(e.value)


def test_answerable_without_citation_is_refused():
    with pytest.raises(ValidationError):
        Answer.model_validate_json(_json(citations=[]), context={"retrieved_ids": RETRIEVED})


def test_unanswerable_must_have_empty_short_answer_and_no_citation():
    with pytest.raises(ValidationError):
        Answer.model_validate_json(_json(answerable=False), context={"retrieved_ids": RETRIEVED})
    ok = Answer.model_validate_json(_json(answerable=False, short_answer="", citations=[]),
                                    context={"retrieved_ids": RETRIEVED})
    assert ok.answerable is False


def test_duplicate_citations_are_merged():
    a = Answer.model_validate_json(_json(citations=["02-delivery#0", "02-delivery#0"]),
                                   context={"retrieved_ids": RETRIEVED})
    assert a.citations == ["02-delivery#0"]


def test_cot_reasoning_comes_first():
    assert list(AnswerCoT.model_fields)[0] == "reasoning"


# --- src/llm.py with a fake client: re-prompt at most twice, check stop_reason, log every call

class FakeClient:
    """Answers with the texts given, in order, and records every request."""

    def __init__(self, texts, stop_reason="end_turn"):
        self.texts, self.stop_reason, self.requests = list(texts), stop_reason, []
        self.messages = self

    def create(self, **kw):
        self.requests.append(kw)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.texts.pop(0))],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
            stop_reason=self.stop_reason, _request_id="req_test")


def _call(client, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CALLS_LOG", tmp_path / "calls.csv")
    return llm.structured_call(model="claude-haiku-5-5", system="s", user="q", schema=Answer,
                               context={"retrieved_ids": RETRIEVED}, client=client, tag="test")


def test_valid_at_first_answer(tmp_path, monkeypatch):
    r = _call(FakeClient([_json()]), tmp_path, monkeypatch)
    assert r.ok and len(r.attempts) == 1
    assert (tmp_path / "calls.csv").read_text().count("\n") == 2       # header + one row


def test_reprompt_with_the_error_then_valid(tmp_path, monkeypatch):
    client = FakeClient([_json(citations=["02-delivery#5"]), _json()])
    r = _call(client, tmp_path, monkeypatch)
    assert r.ok and r.reprompts == 1
    reprompt = client.requests[1]["messages"][-1]["content"]
    assert "02-delivery#5" in reprompt                                  # the error is sent back to the model


def test_gives_up_after_two_reprompts(tmp_path, monkeypatch):
    client = FakeClient([_json(citations=["nope#1"])] * 5)
    r = _call(client, tmp_path, monkeypatch)
    assert not r.ok and len(client.requests) == 3 and "gave up" in r.failure


@pytest.mark.parametrize("stop", ["max_tokens", "refusal"])
def test_stop_reason_checked_before_the_text(tmp_path, monkeypatch, stop):
    client = FakeClient([_json()], stop_reason=stop)
    r = _call(client, tmp_path, monkeypatch)
    assert not r.ok and len(client.requests) == 1 and stop in r.failure


def test_one_retry_layer_only():
    import inspect
    src = inspect.getsource(llm)
    assert "tenacity" not in src.replace("No tenacity", "")              # no second layer on top of the SDK's


def test_cost_uses_each_price():
    usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000)
    assert llm.cost("claude-haiku-5-5", usage) == pytest.approx(0.60)
    assert llm.cost("claude-sonnet-5-5", usage) == pytest.approx(12.0)
