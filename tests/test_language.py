"""Tests for language detection, using the real questions and answers from the first eval run."""

import pytest

from copilot.answer import build_messages
from copilot.evaluate import missing_facts
from copilot.language import detect_language
from copilot.search import SearchResult


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # questions from data/eval/questions.yaml
        ("What is the Wohnungsgeberbestätigung and who gives it to me?", "en"),
        ("Does a bank have to give me a basic account if I just arrived in Germany?", "en"),
        ("Do I need health insurance to enrol at a German university?", "en"),
        ("Innerhalb welcher Frist muss ich mich nach dem Einzug anmelden?", "de"),
        ("Wie hoch darf die Mietkaution sein?", "de"),
        # real answers from the Nov 25 run (English questions answered in German)
        ("Ja, du musst in Deutschland krankenversichert sein, um dich einzuschreiben [3].", "de"),
        ("Ja, grundsätzlich muss eine Bank Ihnen ein Basiskonto anbieten [3].", "de"),
        ("You apply at the local Foreigners Authority (Ausländerbehörde) in Berlin [1].", "en"),
    ],
)
def test_detect_language(text, expected):
    assert detect_language(text) == expected


def test_prompt_states_the_answer_language_last():
    passage = SearchResult("1", "https://example.berlin", "banking", "", "Text auf Deutsch.", 0.7)
    english = build_messages("Does a bank have to give me an account?", [passage])
    german = build_messages("Muss mir die Bank ein Konto geben?", [passage])
    assert english[1]["content"].endswith("Answer in English.")
    assert german[1]["content"].endswith("Answer in German.")


def test_fact_check_ignores_non_breaking_spaces():
    # Real case: "innerhalb von 14 Tagen" was marked as missing "14 Tagen".
    answer = "Sie müssen sich innerhalb von 14 Tagen anmelden [1]."
    assert missing_facts(answer, ["zwei Wochen|14 Tage|14 Tagen"]) == []
