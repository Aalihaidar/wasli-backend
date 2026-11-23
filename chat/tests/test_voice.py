"""The voice endpoint: a clip is understood like a typed message and never stored."""

import uuid
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import TemporaryUploadedFile
from django.utils import timezone

from assistant.errors import (
    AssistantBudgetExceeded,
    AssistantError,
    AssistantInvalidOutput,
    AssistantTimeout,
)
from assistant.models import AICallLog
from assistant.types import AudioInput, OrderIntent
from chat.models import Conversation, ConversationState, Message
from chat.tests.helpers import (
    add,
    bot_texts,
    heard,
    make_wav,
    make_world,
    open_chat,
    say_text,
    say_voice,
    scripted,
    signed_in,
    summary_of,
)

pytestmark = pytest.mark.django_db


def _chat(monkeypatch: pytest.MonkeyPatch, transcript: str | None = "two karak"):  # type: ignore[no-untyped-def]
    world = make_world()
    adapter = heard(monkeypatch, transcript, add(world.karak, 2))
    _, api = signed_in()
    conversation_id = open_chat(api).json()["conversation"]["id"]
    return world, adapter, api, conversation_id


class TestUnderstandingAClip:
    def test_a_spoken_order_is_understood_and_the_words_are_kept_as_the_transcript(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)

        response = say_voice(api, conversation_id, make_wav())

        assert response.status_code == 201
        customer, bot = response.json()["messages"]
        assert customer["sender"] == "customer" and customer["used_voice"] is True
        assert customer["transcript"] == "two karak" and customer["text"] == ""
        assert bot["kind"] == "order_summary"
        assert summary_of(response)["lines"][0]["quantity"] == 2

    def test_the_clip_reaches_the_assistant_in_memory_as_wav(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, adapter, api, conversation_id = _chat(monkeypatch)
        clip = make_wav(2.0)

        say_voice(api, conversation_id, clip)

        (call,) = adapter.calls
        assert call.message == AudioInput(data=clip, mime_type="audio/wav")

    def test_nothing_of_the_audio_is_stored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)
        clip = make_wav(2.0)

        say_voice(api, conversation_id, clip)

        for message in Message.objects.all():
            assert clip not in repr(message.payload).encode()
            assert not message.image
        stored = Message.objects.get(used_voice=True)
        assert stored.transcript == "two karak" and stored.payload == {}
        assert not AICallLog.objects.filter(error_code__contains="RIFF").exists()

    def test_the_upload_never_touches_the_disk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)

        def refuse(*args: object, **kwargs: object) -> None:
            raise AssertionError("an uploaded file was written to a temporary file")

        monkeypatch.setattr(TemporaryUploadedFile, "__init__", refuse)

        # 3 MB: over Django's default memory threshold (2.5 MB), which would use a temp file.
        response = say_voice(api, conversation_id, make_wav(25, rate=64000))

        assert response.status_code == 201

    def test_the_call_is_logged_as_audio_without_its_content(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        scripted(monkeypatch)  # the recorded fake: nothing scripted for this clip
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        say_voice(api, conversation_id, make_wav())

        (log,) = AICallLog.objects.all()
        assert (log.purpose, log.input_kind) == ("parse_order", "audio")
        assert world.restaurant.pk == log.restaurant_id

    def test_a_replayed_client_message_id_returns_the_first_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, adapter, api, conversation_id = _chat(monkeypatch)
        same = uuid.uuid4()

        first = say_voice(api, conversation_id, make_wav(), same)
        again = say_voice(api, conversation_id, make_wav(), same)

        assert again.status_code == 201
        assert again.json()["messages"] == first.json()["messages"]
        assert len(adapter.calls) == 1
        assert Message.objects.filter(client_message_id=same).count() == 1

    def test_a_spoken_confirm_moves_on_like_the_button(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = make_world()
        heard(monkeypatch, "that is all", intent=OrderIntent.CONFIRM)
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]
        Conversation.objects.filter(pk=conversation_id).update(
            lines=[
                {
                    "line": 1,
                    "item_id": str(world.karak.pk),
                    "quantity": 1,
                    "option_ids": [],
                    "note": "",
                }
            ]
        )

        response = say_voice(api, conversation_id, make_wav())

        assert response.json()["conversation"]["state"] == "ask_car"

    def test_a_voice_message_moves_the_expiry_forward(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)
        Conversation.objects.filter(pk=conversation_id).update(
            expires_at=timezone.now() + timedelta(minutes=1)
        )

        say_voice(api, conversation_id, make_wav())

        left = Conversation.objects.get(pk=conversation_id).expires_at - timezone.now()
        assert left > timedelta(minutes=50)


class TestWhenTheClipCannotBeUsed:
    def test_a_clip_with_no_words_is_stored_with_an_empty_transcript_and_asked_again(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch, transcript=None)

        response = say_voice(api, conversation_id, make_wav())

        assert response.status_code == 201
        customer, bot = response.json()["messages"]
        assert customer["used_voice"] is True and customer["transcript"] == ""
        assert bot["text"] == "Sorry, I could not hear that. Please say it again."
        assert response.json()["conversation"]["ai_available"] is True
        assert Conversation.objects.get(pk=conversation_id).lines == []

    def test_a_blank_transcript_is_the_same_as_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch, transcript="   ")

        response = say_voice(api, conversation_id, make_wav())

        assert bot_texts(response)[0].startswith("Sorry, I could not hear")

    def test_the_bot_asks_again_in_arabic_for_an_arabic_conversation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        heard(monkeypatch, None)
        _, api = signed_in()
        conversation_id = open_chat(api, locale="ar").json()["conversation"]["id"]

        response = say_voice(api, conversation_id, make_wav())

        assert "لم أسمع" in bot_texts(response)[0]

    @pytest.mark.parametrize("code", ["http_400", "http_413", "http_415", "http_422"])
    def test_a_clip_the_provider_cannot_read_is_asked_again_and_the_assistant_stays_on(
        self, monkeypatch: pytest.MonkeyPatch, code: str
    ) -> None:
        make_world()
        scripted(monkeypatch, fail_with=AssistantError(code))
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_voice(api, conversation_id, make_wav())

        assert bot_texts(response)[0].startswith("Sorry, I could not hear")
        assert response.json()["conversation"]["ai_available"] is True

    def test_a_provider_outage_is_answered_in_the_chat_and_turns_the_assistant_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        adapter = scripted(monkeypatch, fail_with=AssistantTimeout())
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        first = say_voice(api, conversation_id, make_wav())
        second = say_voice(api, conversation_id, make_wav())

        assert first.status_code == second.status_code == 201
        assert first.json()["messages"][0]["transcript"] == ""
        assert "cannot understand voice messages" in bot_texts(first)[0]
        assert first.json()["conversation"]["ai_available"] is False
        assert "cannot understand voice messages" in bot_texts(second)[0]
        assert len(adapter.calls) == 1  # the second clip never reached the provider

    def test_a_used_up_budget_is_answered_in_the_chat_without_an_outage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        scripted(monkeypatch, fail_with=AssistantBudgetExceeded())
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_voice(api, conversation_id, make_wav())

        assert "cannot understand voice messages" in bot_texts(response)[0]
        assert response.json()["conversation"]["ai_available"] is True

    def test_a_badly_formed_answer_is_not_understood_and_not_an_outage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_world()
        scripted(monkeypatch, fail_with=AssistantInvalidOutput())
        _, api = signed_in()
        conversation_id = open_chat(api).json()["conversation"]["id"]

        response = say_voice(api, conversation_id, make_wav())

        assert bot_texts(response)[0].startswith("Sorry, I did not understand")
        assert response.json()["conversation"]["ai_available"] is True

    def test_while_the_assistant_is_off_no_clip_is_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, adapter, api, conversation_id = _chat(monkeypatch)
        say_text(api, conversation_id, "typed one")  # fine, makes a call
        from assistant.availability import record_failure

        record_failure()
        calls_before = len(adapter.calls)

        response = say_voice(api, conversation_id, make_wav())

        assert "cannot understand voice messages" in bot_texts(response)[0]
        assert len(adapter.calls) == calls_before


class TestTheUpload:
    def test_a_missing_clip_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)

        response = say_voice(api, conversation_id, None)

        assert response.status_code == 400
        assert response.json()["errors"][0]["attr"] == "audio"

    def test_a_missing_client_message_id_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        _, _, api, conversation_id = _chat(monkeypatch)

        response = api.post(
            f"/api/v1/conversations/{conversation_id}/voice",
            {"audio": SimpleUploadedFile("c.wav", make_wav(), "audio/wav")},
            format="multipart",
        )

        assert response.status_code == 400

    @pytest.mark.parametrize(
        "content_type", ["audio/mpeg", "audio/mp4", "audio/webm", "text/plain", ""]
    )
    def test_only_wav_is_accepted_for_now(
        self, monkeypatch: pytest.MonkeyPatch, content_type: str
    ) -> None:
        _, adapter, api, conversation_id = _chat(monkeypatch)

        response = say_voice(
            api, conversation_id, make_wav(), content_type=content_type
        )

        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "unsupported_audio_format"
        assert adapter.calls == []
        assert not Message.objects.filter(used_voice=True).exists()

    @pytest.mark.parametrize("content_type", ["audio/x-wav", "audio/wave", "audio/WAV"])
    def test_the_usual_names_of_wav_are_accepted(
        self, monkeypatch: pytest.MonkeyPatch, content_type: str
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)

        response = say_voice(
            api, conversation_id, make_wav(), content_type=content_type
        )

        assert response.status_code == 201

    def test_bytes_that_are_not_a_wav_are_refused_even_with_the_right_type(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)

        response = say_voice(api, conversation_id, b"this is not audio at all")

        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "unsupported_audio_format"

    def test_an_empty_file_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)

        assert say_voice(api, conversation_id, b"").status_code == 400

    def test_a_clip_without_any_sound_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)

        response = say_voice(api, conversation_id, make_wav(0))

        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "unsupported_audio_format"

    def test_a_minute_is_accepted_and_a_little_more_is_not(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)

        ok = say_voice(api, conversation_id, make_wav(60.0))
        too_long = say_voice(api, conversation_id, make_wav(60.5))

        assert ok.status_code == 201
        assert too_long.status_code == 400
        assert too_long.json()["errors"][0]["code"] == "audio_too_long"

    def test_a_clip_just_under_5_mb_is_accepted_and_read_in_memory(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, adapter, api, conversation_id = _chat(monkeypatch)
        clip = make_wav(29.0, rate=88000)  # about 5.1 MB, under both caps

        response = say_voice(api, conversation_id, clip)

        assert len(clip) < 5 * 1024 * 1024
        assert response.status_code == 201
        assert adapter.calls[0].message.data == clip

    def test_a_clip_over_5_mb_is_too_large(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, adapter, api, conversation_id = _chat(monkeypatch)

        response = say_voice(
            api, conversation_id, make_wav(1.0) + b"\x00" * (5 * 1024 * 1024)
        )

        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "audio_too_large"
        assert adapter.calls == []

    def test_a_request_over_6_mb_is_refused_before_anything_reads_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, adapter, api, conversation_id = _chat(monkeypatch)

        response = say_voice(api, conversation_id, b"\x00" * (6 * 1024 * 1024 + 1))

        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "audio_too_large"
        assert adapter.calls == []

    def test_a_refused_clip_leaves_no_message_behind(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)

        say_voice(api, conversation_id, make_wav(61))

        assert Message.objects.filter(sender="customer").count() == 0


class TestWhoMayUseIt:
    def test_a_customer_token_is_required(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rest_framework.test import APIClient

        _, _, _, conversation_id = _chat(monkeypatch)

        assert say_voice(APIClient(), conversation_id, make_wav()).status_code == 401

    def test_another_customers_conversation_is_a_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, adapter, _, conversation_id = _chat(monkeypatch)
        _, intruder = signed_in("intruder-voice@example.com")

        response = say_voice(intruder, conversation_id, make_wav())

        assert response.status_code == 404
        assert adapter.calls == []

    def test_an_unknown_conversation_is_a_404(self) -> None:
        _, api = signed_in()

        assert say_voice(api, str(uuid.uuid4()), make_wav()).status_code == 404

    @pytest.mark.parametrize("state", ["ask_car", "ask_note", "review"])
    def test_the_later_open_steps_take_voice_as_their_own_answer(
        self, monkeypatch: pytest.MonkeyPatch, state: str
    ) -> None:
        _, adapter, api, conversation_id = _chat(monkeypatch)
        Conversation.objects.filter(pk=conversation_id).update(state=state, lines=[])

        response = say_voice(api, conversation_id, make_wav())

        assert response.status_code == 201
        assert response.json()["messages"][0]["used_voice"] is True
        # The order parser is for the ordering step only; each step reads the clip its own way.
        assert not [c for c in adapter.calls if c.purpose == "parse_order"]

    def test_a_placed_conversation_takes_no_voice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)
        Conversation.objects.filter(pk=conversation_id).update(
            state=ConversationState.PLACED
        )

        assert say_voice(api, conversation_id, make_wav()).status_code == 409

    def test_an_expired_conversation_refuses_voice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, api, conversation_id = _chat(monkeypatch)
        Conversation.objects.filter(pk=conversation_id).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        response = say_voice(api, conversation_id, make_wav())

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "conversation_expired"
        assert Message.objects.filter(sender="customer").count() == 0
