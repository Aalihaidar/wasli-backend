import pytest

from customers.texts import BODIES, SUBJECTS, code_message
from customers.verification import Purpose


@pytest.mark.parametrize("purpose", list(Purpose))
def test_every_purpose_has_both_languages(purpose: str) -> None:
    assert set(SUBJECTS[purpose]) == {"en", "ar"}
    assert set(BODIES[purpose]) == {"en", "ar"}


@pytest.mark.parametrize("purpose", list(Purpose))
@pytest.mark.parametrize("locale", ["en", "ar"])
def test_the_message_carries_the_code_and_how_long_it_lasts(
    purpose: str, locale: str
) -> None:
    subject, body = code_message(purpose, locale, "123456", 10)

    assert subject
    assert "123456" in body and "10" in body


def test_the_arabic_message_is_arabic_and_the_english_is_not() -> None:
    _, arabic = code_message(Purpose.SIGNUP, "ar", "123456", 10)
    _, english = code_message(Purpose.SIGNUP, "en", "123456", 10)

    assert any("؀" <= ch <= "ۿ" for ch in arabic)
    assert not any("؀" <= ch <= "ۿ" for ch in english)


def test_an_unknown_language_falls_back_to_english() -> None:
    assert code_message(Purpose.SIGNUP, "fr", "123456", 10) == code_message(
        Purpose.SIGNUP, "en", "123456", 10
    )


def test_a_reset_message_says_it_is_a_reset() -> None:
    _, body = code_message(Purpose.PASSWORD_RESET, "en", "123456", 10)

    assert "reset" in body.lower()
