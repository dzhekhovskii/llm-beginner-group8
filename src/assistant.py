"""The component: a customer question in, a checked, cited, safe answer out.

    python -m src.assistant "Can I pay by bank transfer?"                 # zero-shot, the component's model
    python -m src.assistant "Puis-je payer en espèces ?" --strategy cot

Pipeline: retrieve the K nearest passages -> build the system prompt from the strategy's prompt file, with the
help-centre passages and the (sanitised) seller passages in two separate fields -> one structured call through
src/llm.py (checked against our rules, re-prompted at most twice) -> output check -> what is sent.
"""

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from src import guardrails, llm
from src.retrieve import HelpCentre, is_untrusted
from src.schema import Answer, AnswerCoT

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"

# strategy -> (prompt file, answer shape). A prompt that produced a figure is never edited: copy it to a new file.
STRATEGIES = {
    "zero_shot": ("answer_zero_shot.md", Answer),
    "few_shot": ("answer_few_shot.md", Answer),
    "cot": ("answer_cot.md", AnswerCoT),
}


def load_prompt(filename):
    """A prompt file holds two ```text blocks: the system prompt, then the user message.
    Returns (system_template, user_template)."""
    blocks = re.findall(r"```text\n(.*?)\n```", (PROMPTS / filename).read_text(encoding="utf-8"), re.DOTALL)
    if len(blocks) < 2:
        raise ValueError(f"{filename}: expected two ```text blocks (system prompt, then user message)")
    return blocks[0], blocks[1]


def format_passages(passages):
    return "\n\n".join(f"[{p['id']}] {p['text']}" for p in passages) or "(none)"


def build_system(template, passages):
    """Fill the prompt's two fields. OUR code decides the field from the passage's id: a seller cannot write
    their way into <help_centre>. Seller text is sanitised before the model sees it."""
    policy = [p for p in passages if not is_untrusted(p["id"])]
    seller = [p for p in passages if is_untrusted(p["id"])]
    return template.replace("{policy}", format_passages(policy)).replace(
        "{seller}", guardrails.sanitise(format_passages(seller)))


@dataclass
class Reply:
    question: str
    strategy: str
    model: str
    passages: list
    record: object = None            # the checked Answer / AnswerCoT, or None when the call gave up
    sent: str = ""                   # what the customer actually receives
    blocked: list = field(default_factory=list)
    failure: str | None = None
    attempts: list = field(default_factory=list)

    @property
    def cost_usd(self):
        return sum(a["cost_usd"] for a in self.attempts)

    @property
    def ms(self):
        return sum(a["ms"] for a in self.attempts)


_centre = None


def get_centre():
    global _centre
    if _centre is None:
        _centre = HelpCentre()
    return _centre


def answer(question, strategy="zero_shot", model=llm.COMPONENT_MODEL, centre=None, extra_passages=(),
           tag="", client=None):
    """Answer one question. extra_passages: passages added to the retrieved ones (used by the injection tests
    to plant a document, as if it had been retrieved)."""
    centre = centre or get_centre()
    prompt_file, shape = STRATEGIES[strategy]
    system_t, user_t = load_prompt(prompt_file)
    passages = centre.retrieve(question) + list(extra_passages)
    result = llm.structured_call(
        model=model, system=build_system(system_t, passages), user=user_t.replace("{question}", question),
        schema=shape, context={"retrieved_ids": {p["id"] for p in passages}},
        tag=tag or strategy, client=client)
    reply = Reply(question, strategy, model, passages, attempts=result.attempts)
    if not result.ok:
        reply.failure, reply.sent = result.failure, guardrails.FALLBACK_FAILED
        return reply
    reply.record = result.record
    reply.sent, reply.blocked = guardrails.safe_reply(result.record.answer)
    return reply


class ClosedBook(BaseModel):
    answer: str


def closed_book(question, model=llm.COMPONENT_MODEL):
    """The same model with NO passage: what it says from training alone (the evidence for decision 0003)."""
    r = llm.structured_call(model=model, system="You are the customer assistant of Albert's Marketplace, an online "
                            "beauty marketplace. Answer the customer's question.", user=question,
                            schema=ClosedBook, tag="closed_book")
    return r.record.answer if r.ok else f"(failed: {r.failure})"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Ask the component one question.")
    ap.add_argument("question")
    ap.add_argument("--strategy", choices=STRATEGIES, default="zero_shot")
    ap.add_argument("--model", default=llm.COMPONENT_MODEL)
    ap.add_argument("--closed-book", action="store_true", help="no retrieval: what the model says on its own")
    a = ap.parse_args()
    if a.closed_book:
        print("CLOSED BOOK:", closed_book(a.question, a.model))
        raise SystemExit
    r = answer(a.question, a.strategy, a.model, tag=f"cli:{a.strategy}")
    print("retrieved:", [p["id"] for p in r.passages])
    if r.record is not None:
        print("record:", r.record.model_dump_json(indent=2))
    print("blocked:" if r.blocked else "", r.blocked or "")
    print("SENT:", r.sent)
    print(f"{len(r.attempts)} call(s), ${r.cost_usd:.5f}, {r.ms} ms" + (f", failure: {r.failure}" if r.failure else ""))
