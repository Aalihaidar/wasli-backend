"""Checking a voice upload before anything reads it.

Voice is never stored: the clip is read into memory, sent to the assistant and dropped, and only
its transcript stays on the customer's message. This module decides whether a clip may be sent at
all. Only WAV is accepted for now (the recorded clip of the customer app; other types come once
they have been tried), and a clip is at most 30 seconds and 5 MB. Each refusal is a stable error
code on the ``audio`` field.
"""

import io
import wave
from typing import Any

from rest_framework import serializers

from assistant import limits
from assistant.types import AudioInput

# The media types a WAV clip is sent as. The file itself is checked too: a type that says WAV
# over bytes that are not one is refused.
WAV_TYPES = frozenset({"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"})


def read_voice_upload(upload: Any) -> AudioInput:
    """The clip in an uploaded file, or a ``400`` with ``audio_too_large``,
    ``unsupported_audio_format`` or ``audio_too_long``."""
    if upload.size > limits.MAX_AUDIO_BYTES:
        raise serializers.ValidationError(
            "The clip is larger than 5 MB.", code="audio_too_large"
        )
    media_type = (upload.content_type or "").split(";")[0].strip().lower()
    if media_type not in WAV_TYPES:
        raise serializers.ValidationError(
            "Send the clip as a WAV file.", code="unsupported_audio_format"
        )
    data = upload.read()
    try:
        with wave.open(io.BytesIO(data)) as clip:
            frames, rate = clip.getnframes(), clip.getframerate()
    except wave.Error, EOFError:
        raise serializers.ValidationError(
            "The file is not a readable WAV clip.", code="unsupported_audio_format"
        ) from None
    if rate <= 0 or frames <= 0:
        raise serializers.ValidationError(
            "The clip has no sound.", code="unsupported_audio_format"
        )
    if frames / rate > limits.MAX_AUDIO_SECONDS:
        raise serializers.ValidationError(
            "The clip is longer than 30 seconds.", code="audio_too_long"
        )
    return AudioInput(data=data, mime_type="audio/wav")
