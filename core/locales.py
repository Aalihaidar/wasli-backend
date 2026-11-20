"""The two languages of the product. Text shown to customers is written in the
conversation's locale; a customer's own default is stored on their profile."""

from enum import StrEnum


class Locale(StrEnum):
    EN = "en"
    AR = "ar"


LOCALE_CHOICES = [(Locale.EN.value, "English"), (Locale.AR.value, "العربية")]

ARABIC_OPTIONAL_HELP = "Optional. Leave empty when there is no Arabic text: the English text is shown instead."


def arabic_or_english(arabic: str, english: str) -> str:
    """The Arabic text of a pair, or the English text when the Arabic one is empty.

    A restaurant whose menu is in English only leaves every ``*_ar`` field empty. The empty value
    is kept in the database (a copy of the English text would go stale when it is renamed) and
    this fallback is applied wherever the text is read: the API, the assistant's menu and the
    copies an order keeps.
    """
    return arabic.strip() or english


class ArabicFallbackMixin:
    """For a model with a ``name_en`` / ``name_ar`` pair: ``name_ar_display`` is the Arabic name,
    or the English name when there is no Arabic one."""

    name_en: str
    name_ar: str

    @property
    def name_ar_display(self) -> str:
        return arabic_or_english(self.name_ar, self.name_en)
