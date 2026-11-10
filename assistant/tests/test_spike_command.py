import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.management import CommandError, call_command

from assistant.models import AICallLog
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db


def spike(*args: str) -> str:
    out = StringIO()
    call_command("assistant_spike", *args, stdout=out)
    return out.getvalue()


def test_a_car_answer_is_sent_and_the_result_printed() -> None:
    text = spike(
        "car", "--text", "Parking B2 near the lift, plate A 12345, white Toyota Camry"
    )

    assert "Provider: fake" in text
    assert '"plate": "A 12345"' in text
    assert "1 of 1 calls ok" in text
    assert "audio/wav" in text  # the accepted audio types are reported


def test_the_call_is_logged_like_any_other() -> None:
    spike("reply", "--text", "yes")

    call = AICallLog.objects.get()
    assert (call.purpose, call.outcome, call.restaurant) == (
        "classify_reply",
        "ok",
        None,
    )


def test_repeat_calls_several_times() -> None:
    text = spike("reply", "--text", "yes", "--repeat", "3")

    assert AICallLog.objects.count() == 3
    assert "3 of 3 calls ok" in text


@pytest.mark.parametrize("repeat", ["0", "6", "-1"])
def test_repeat_is_between_one_and_five(repeat: str) -> None:
    with pytest.raises(CommandError, match="--repeat"):
        spike("reply", "--text", "yes", "--repeat", repeat)


def test_an_order_uses_an_invented_menu_by_default() -> None:
    text = spike("order", "--text", "two karak")

    assert (
        '"intent": "unclear"' in text
    )  # the fake understands nothing it was not given


def test_an_order_can_use_a_restaurants_own_menu() -> None:
    make_restaurant("cafe-a")

    assert "ok" in spike("order", "--text", "two karak", "--restaurant", "cafe-a")


def test_an_unknown_restaurant_is_refused() -> None:
    with pytest.raises(CommandError, match="nowhere"):
        spike("order", "--text", "x", "--restaurant", "nowhere")


def test_a_clip_is_sent_with_its_type(tmp_path: Path) -> None:
    clip = tmp_path / "note.wav"
    clip.write_bytes(b"no straw please")

    text = spike("transcribe", "--audio", str(clip))

    assert (
        json.loads(text[text.index("{") : text.rindex("}") + 1])["transcript"]
        == "No straw please"
    )
    assert AICallLog.objects.get().input_kind == "audio"


@pytest.mark.parametrize("name", ["note.m4a", "note.txt", "note"])
def test_an_unsupported_clip_extension_is_refused(tmp_path: Path, name: str) -> None:
    clip = tmp_path / name
    clip.write_bytes(b"x")

    with pytest.raises(CommandError, match="Unsupported audio extension"):
        spike("transcribe", "--audio", str(clip))


def test_a_clip_over_five_megabytes_is_refused(tmp_path: Path) -> None:
    clip = tmp_path / "big.wav"
    clip.write_bytes(b"x" * (5 * 1024 * 1024 + 1))

    with pytest.raises(CommandError, match="larger than 5 MB"):
        spike("transcribe", "--audio", str(clip))


def test_a_missing_clip_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="Cannot read"):
        spike("transcribe", "--audio", str(tmp_path / "gone.wav"))


def test_transcribe_needs_audio() -> None:
    with pytest.raises(CommandError, match="needs --audio"):
        spike("transcribe", "--text", "hello")


def test_text_or_audio_is_required() -> None:
    with pytest.raises(CommandError):
        spike("car")


def test_it_never_runs_in_production(settings: Any) -> None:
    settings.ENVIRONMENT = "production"

    with pytest.raises(CommandError, match="never runs in production"):
        spike("reply", "--text", "yes")

    assert not AICallLog.objects.exists()


def test_a_failing_provider_is_reported_not_raised(
    settings: Any, monkeypatch: Any
) -> None:
    from assistant.adapters.fake import FakeAdapter
    from assistant.errors import AssistantTimeout

    monkeypatch.setattr(
        "assistant.services.get_adapter",
        lambda: FakeAdapter(fail_with=AssistantTimeout()),
    )

    text = spike("reply", "--text", "yes")

    assert "failed: timeout" in text
    assert AICallLog.objects.get().outcome == "timeout"
