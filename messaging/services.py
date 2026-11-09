from .backends import OutgoingMessage, get_backend
from .models import Channel, Purpose


def send_message(
    channel: Channel,
    recipient: str,
    body: str,
    purpose: Purpose,
    *,
    subject: str = "",
) -> None:
    """Send one email or SMS through the configured backend. The only way the project sends."""
    get_backend().send(
        OutgoingMessage(
            channel=channel.value,
            recipient=recipient,
            body=body,
            purpose=purpose.value,
            subject=subject,
        )
    )
