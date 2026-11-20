"""The Arabic-or-English fallback used wherever a bilingual text is read."""

import pytest

from core.locales import arabic_or_english


@pytest.mark.parametrize(
    ("arabic", "english", "expected"),
    [
        ("شاي كرك", "Karak tea", "شاي كرك"),
        ("", "Karak tea", "Karak tea"),
        ("   ", "Karak tea", "Karak tea"),
        ("\n", "Karak tea", "Karak tea"),
        ("", "", ""),
    ],
)
def test_the_english_text_stands_in_for_a_missing_arabic_one(
    arabic: str, english: str, expected: str
) -> None:
    assert arabic_or_english(arabic, english) == expected


def test_the_arabic_text_is_returned_without_stray_spaces() -> None:
    assert arabic_or_english(" شاي ", "Tea") == "شاي"
