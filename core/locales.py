"""The two languages of the product. Text shown to customers is written in the
conversation's locale; a customer's own default is stored on their profile."""

from enum import StrEnum


class Locale(StrEnum):
    EN = "en"
    AR = "ar"


LOCALE_CHOICES = [(Locale.EN.value, "English"), (Locale.AR.value, "العربية")]
