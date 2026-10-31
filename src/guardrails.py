"""Untrusted text, handled as untrusted: before the model (sanitiser) and after it (output check).

What we treat as UNTRUSTED (docs/decisions/0005-guardrails.md):
  - the sellers' product pages (05-) and the product catalogue (06-): written by third-party sellers;
  - the customer's question: anyone can type anything;
and as trusted: Albert's Marketplace's own help-centre pages (01- to 04-).

Three layers, none complete alone (lesson 3: the prompt alone obeyed a seller's page 5 times out of 5):
  1. separation (src/assistant.py): help-centre passages and seller passages go in two labelled fields of the
     system prompt, chosen by OUR code from the passage id, never by the text; the question goes in the user
     message, never in the system prompt;
  2. sanitise(): sentences of untrusted passages that read like instructions are removed before the model;
  3. output_check(): after the model, an answer that carries a contact the company does not publish
     (e-mail, link, IBAN, phone number) is NOT sent. This is the only layer that held against a carrier's note
     with no instruction words in it (lesson 4).
"""

import re

INSTRUCTION_LIKE = re.compile(
    r"[^.]*\b(ignore|instructions?|AI assistants?|assistants?|support systems?|chatbots?|language models?|"
    r"tell (them|the customer|customers)|do not mention|must (email|e-mail|write|contact)|contact the seller|"
    r"previous|system prompt)\b[^.]*\.",
    re.IGNORECASE)

# The only contact Albert's Marketplace publishes in its help centre (03-payments-and-account).
ALLOWED_CONTACTS = {"privacy@albertsmarketplace.example"}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}\b")
PHONE = re.compile(r"\+\d[\d ().-]{7,}\d")

FALLBACK_BLOCKED = ("I'm sorry, I can't share that. For anything about your order, please contact "
                    "Albert's Marketplace support from your order page.")
FALLBACK_FAILED = ("I'm sorry, I couldn't find a reliable answer to your question. A member of our support "
                   "team will get back to you.")


def sanitise(text):
    """Remove the sentences of untrusted text that read like instructions."""
    return INSTRUCTION_LIKE.sub("", text)


def output_check(text):
    """Every contact in the answer that the company does not publish: e-mails, links, IBANs, phone numbers."""
    found = set(m.rstrip(".,;:)") for m in EMAIL.findall(text))
    found |= set(m.rstrip(".,;:)") for m in URL.findall(text))
    found |= set(IBAN.findall(text)) | set(PHONE.findall(text))
    return sorted(f for f in found if f.lower() not in ALLOWED_CONTACTS)


def safe_reply(answer_text):
    """What is actually SENT to the customer: the answer, or the fallback if the output check blocks it.
    Returns (text_sent, blocked), blocked being the list of contacts that stopped it (empty when sent as is)."""
    blocked = output_check(answer_text)
    return (FALLBACK_BLOCKED, blocked) if blocked else (answer_text, [])
