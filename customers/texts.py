"""The messages that carry a verification code, in Arabic and English.

The backend writes every message a customer reads. The language is the customer's ``locale``.
A test checks that every purpose has both languages.
"""

from .models import VerificationCode

Purpose = VerificationCode.Purpose

SUBJECTS: dict[str, dict[str, str]] = {
    Purpose.SIGNUP: {
        "en": "Your Wasli verification code",
        "ar": "رمز التحقق في وصلي",
    },
    Purpose.CONTACT: {
        "en": "Your Wasli verification code",
        "ar": "رمز التحقق في وصلي",
    },
    Purpose.PASSWORD_RESET: {
        "en": "Your Wasli password reset code",
        "ar": "رمز إعادة تعيين كلمة المرور في وصلي",
    },
}

BODIES: dict[str, dict[str, str]] = {
    Purpose.SIGNUP: {
        "en": (
            "Your Wasli verification code is {code}. It is valid for {minutes} minutes. "
            "If you did not ask for it, ignore this message."
        ),
        "ar": (
            "رمز التحقق الخاص بك في وصلي هو {code}. صالح لمدة {minutes} دقائق. "
            "إذا لم تطلبه فتجاهل هذه الرسالة."
        ),
    },
    Purpose.CONTACT: {
        "en": (
            "Your Wasli verification code is {code}. It is valid for {minutes} minutes. "
            "If you did not ask for it, ignore this message."
        ),
        "ar": (
            "رمز التحقق الخاص بك في وصلي هو {code}. صالح لمدة {minutes} دقائق. "
            "إذا لم تطلبه فتجاهل هذه الرسالة."
        ),
    },
    Purpose.PASSWORD_RESET: {
        "en": (
            "Your Wasli password reset code is {code}. It is valid for {minutes} minutes. "
            "If you did not ask for it, ignore this message."
        ),
        "ar": (
            "رمز إعادة تعيين كلمة المرور في وصلي هو {code}. صالح لمدة {minutes} دقائق. "
            "إذا لم تطلبه فتجاهل هذه الرسالة."
        ),
    },
}


def code_message(purpose: str, locale: str, code: str, minutes: int) -> tuple[str, str]:
    """The subject and the body of the message that carries ``code``."""
    language = locale if locale in ("en", "ar") else "en"
    return (
        SUBJECTS[purpose][language],
        BODIES[purpose][language].format(code=code, minutes=minutes),
    )
