"""The caps of the assistant layer. They protect the free quota and the cost per order, and
they are checked before anything is sent to a provider."""

# A typed answer or message.
MAX_TEXT_CHARS = 500
# One voice clip: at most 60 seconds, and 5 MB (the request cap in config/settings allows a little
# more for the multipart framing).
MAX_AUDIO_SECONDS = 60
MAX_AUDIO_BYTES = 5 * 1024 * 1024
# An order.
MAX_LINES = 20
MAX_QUANTITY = 20
# A note on a line or an order, as the contract says.
MAX_NOTE_CHARS = 200
# A provider's answer is bounded too, so a runaway answer is refused instead of stored.
MAX_TEXT_FIELD_CHARS = 300
MAX_ACTIONS = 40
MAX_UNMATCHED = 10

# The audio types Gemini accepts. The D1 spike reports which ones the browsers' clips really use.
ACCEPTED_AUDIO_TYPES = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/aac",
        "audio/ogg",
        "audio/flac",
        "audio/webm",
        "audio/opus",
    }
)
