from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from .models import Conversation, Message, MessageKind, Sender


@transaction.atomic
def add_message(
    conversation: Conversation,
    sender: Sender,
    kind: MessageKind = MessageKind.TEXT,
    *,
    text: str = "",
    transcript: str = "",
    used_voice: bool = False,
    image: str = "",
    payload: dict[str, Any] | None = None,
    client_message_id: UUID | None = None,
) -> Message:
    """Append a message to a conversation and give it the next ``seq``.

    The conversation row is locked while the number is taken, so two messages saved at the
    same moment never share a ``seq`` and the numbers have no gaps. ``image`` is the stored
    file name of a menu image, not an upload.
    """
    locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
    seq = locked.last_seq + 1
    message = Message.objects.create(
        conversation=locked,
        seq=seq,
        sender=sender,
        kind=kind,
        text=text,
        transcript=transcript,
        used_voice=used_voice,
        image=image,
        payload=payload or {},
        client_message_id=client_message_id,
    )
    Conversation.objects.filter(pk=locked.pk).update(
        last_seq=seq, updated_at=timezone.now()
    )
    conversation.last_seq = seq
    return message
