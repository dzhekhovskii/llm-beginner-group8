"""The shape of every answer the component returns, and the rules a JSON schema cannot express.

The API's structured outputs guarantee the SHAPE (the fields and their types). The validators below check
the RULES, in our code, against what we actually retrieved:

  - every cited passage id was among the passages retrieved for this question (an invented citation is refused);
  - an answerable answer cites at least one passage;
  - an unanswerable answer has an empty short_answer and cites nothing.

The ids of the retrieved passages arrive through Pydantic's validation context:
    Answer.model_validate_json(text, context={"retrieved_ids": {"01-returns-and-refunds#0", ...}})

Each error message tells the model what to do, because src/llm.py sends it back as the re-prompt.
"""

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


def _dedupe(ids):
    """The cited ids, each once, in the order given."""
    return list(dict.fromkeys(i.strip() for i in ids if i.strip()))


def _check_rules(record, info: ValidationInfo):
    """The rules shared by both answer shapes. Returns the record unchanged, or raises ValueError."""
    retrieved = set((info.context or {}).get("retrieved_ids") or [])
    if retrieved:
        invented = [c for c in record.citations if c not in retrieved]
        if invented:
            raise ValueError(
                f"citations {invented} are not among the passages you were given. "
                f"Cite only these ids, exactly as written: {sorted(retrieved)}")
    if record.answerable and not record.citations:
        raise ValueError("answerable is true but citations is empty: cite the id of every passage your answer uses")
    if not record.answerable and record.short_answer.strip():
        raise ValueError("answerable is false, so short_answer must be empty: leave it as \"\"")
    if not record.answerable and record.citations:
        raise ValueError("answerable is false, so citations must be empty: the passages did not answer the question")
    return record


class Answer(BaseModel):
    """Zero-shot and few-shot: the answer, the fact alone, whether the passages answered, and the sources."""

    answer: str = Field(description="the answer to the customer, in full sentences, in the language of the question")
    short_answer: str = Field(description="only the fact that answers the question, in a few words; empty if unanswerable")
    answerable: bool = Field(description="true only if the passages answer the question")
    citations: list[str] = Field(description="the ids of the passages the answer uses, copied exactly")

    @field_validator("citations")
    @classmethod
    def _unique(cls, v):
        return _dedupe(v)

    @model_validator(mode="after")
    def _rules(self, info: ValidationInfo):
        return _check_rules(self, info)


class AnswerCoT(BaseModel):
    """Chain-of-thought: the same record, with the reasoning FIRST, so it is written before the answer."""

    reasoning: str = Field(description="step by step: which passages apply, which conditions or exceptions hold")
    answer: str = Field(description="the answer to the customer, in full sentences, in the language of the question")
    short_answer: str = Field(description="only the fact that answers the question, in a few words; empty if unanswerable")
    answerable: bool = Field(description="true only if the passages answer the question")
    citations: list[str] = Field(description="the ids of the passages the answer uses, copied exactly")

    @field_validator("citations")
    @classmethod
    def _unique(cls, v):
        return _dedupe(v)

    @model_validator(mode="after")
    def _rules(self, info: ValidationInfo):
        return _check_rules(self, info)


class Verdict(BaseModel):
    """What the judge returns for one answer: a reason, then one score from 1 to 5 per rubric criterion."""

    reason: str
    correct: int = Field(description="1 to 5")
    complete: int = Field(description="1 to 5")
    grounded: int = Field(description="1 to 5")
    clear: int = Field(description="1 to 5")

    @model_validator(mode="after")
    def _range(self):
        bad = [k for k in ("correct", "complete", "grounded", "clear") if not 1 <= getattr(self, k) <= 5]
        if bad:
            raise ValueError(f"scores {bad} must be whole numbers from 1 to 5")
        return self


class Choice(BaseModel):
    """What the judge returns when it compares two answers."""

    reason: str
    better: str = Field(description='"A" or "B"')

    @field_validator("better")
    @classmethod
    def _a_or_b(cls, v):
        v = v.strip().upper()[:1]
        if v not in ("A", "B"):
            raise ValueError('better must be "A" or "B"')
        return v
