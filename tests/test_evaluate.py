"""Our normalisation and token F1, on pairs whose answer we know: no key, no download.

    pytest tests/test_evaluate.py
"""

import pytest

from src.evaluate import exact_match, normalise, token_f1


# --- normalisation: code, tested like code (lesson 4: our first version turned every comma into a point)

@pytest.mark.parametrize("a, b", [
    ("The 21 days.", "21 days"),
    ("€4,90", "4,90 €"),
    ("12 %", "12%"),
    ("€3.95", "3,95 €"),
    ("No, card only.", "no card only"),
])
def test_normalise_equal(a, b):
    assert normalise(a) == normalise(b)


def test_normalise_keeps_what_matters():
    assert exact_match("Yes,", "yes.")             # the bug the course hit: "Yes," must still equal "yes"
    assert not exact_match("30 days", "21 days")
    assert not exact_match("€4.90", "€9.80")


def test_token_f1_known_values():
    assert token_f1("21 days", "21 days") == 1.0
    assert token_f1("30 days", "21 days") == 0.5
    assert token_f1("", "") == 1.0
    assert token_f1("yes", "") == 0.0
