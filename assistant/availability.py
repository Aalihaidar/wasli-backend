"""Whether the assistant layer can be used at all, for ``GET /config``.

Today this only looks at the configuration. The daily request budget and the five minutes after
a provider failure (``ai_available`` on a conversation) are added with the assistant layer.
"""

from django.conf import settings


def ai_enabled() -> bool:
    """The fake provider is always usable; the Gemini provider needs its key and model."""
    if settings.AI_PROVIDER == "fake":
        return True
    return bool(settings.GEMINI_API_KEY and settings.GEMINI_MODEL)
