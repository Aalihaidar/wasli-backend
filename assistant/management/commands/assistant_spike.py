"""Developer-only spike: send one text or one audio clip to the configured provider and show
what comes back, how long it took and what it cost in tokens.

    python manage.py assistant_spike car --text "Parking B2 near the lift, plate A 12345, white Toyota Camry"
    python manage.py assistant_spike order --audio clip.wav --locale ar --repeat 3
    python manage.py assistant_spike transcribe --audio clip.webm

It uses ``AI_PROVIDER`` (``fake`` needs no key), or ``--provider`` to send the same input to
another one and compare. Every call is written to ``AICallLog`` like any
other, so the day's quota count includes the spike. It never runs in production, and it prints
only what the developer fed it. Use invented text or recorded test clips, never a customer's.
"""

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError, CommandParser

from assistant import limits
from assistant.errors import AssistantError, AssistantInputError
from assistant.menu import build_prompt_menu
from assistant.models import AICallLog
from assistant.services import Assistant, get_adapter
from assistant.types import (
    AudioInput,
    CarFields,
    MessageInput,
    PromptGroup,
    PromptItem,
    PromptMenu,
    PromptOption,
)
from restaurants.models import Restaurant

AUDIO_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}

# An invented menu, used when no restaurant is named. Ids are fixed so runs can be compared.
SAMPLE_MENU = PromptMenu(
    items=(
        PromptItem(
            id="00000000-0000-4000-8000-000000000001",
            name_en="Karak tea",
            name_ar="شاي كرك",
            aliases=("karak", "chai karak", "كرك"),
            option_groups=(
                PromptGroup(
                    id="00000000-0000-4000-8000-0000000000a1",
                    name_en="Size",
                    name_ar="الحجم",
                    min_select=1,
                    max_select=1,
                    options=(
                        PromptOption(
                            id="00000000-0000-4000-8000-0000000000b1",
                            name_en="Small",
                            name_ar="صغير",
                            is_default=True,
                        ),
                        PromptOption(
                            id="00000000-0000-4000-8000-0000000000b2",
                            name_en="Large",
                            name_ar="كبير",
                        ),
                    ),
                ),
            ),
        ),
        PromptItem(
            id="00000000-0000-4000-8000-000000000002",
            name_en="Cheese sandwich",
            name_ar="ساندويتش جبنة",
            aliases=("cheese toast",),
        ),
        PromptItem(
            id="00000000-0000-4000-8000-000000000003",
            name_en="Chicken burger",
            name_ar="برجر دجاج",
        ),
        PromptItem(
            id="00000000-0000-4000-8000-000000000004",
            name_en="Beef burger",
            name_ar="برجر لحم",
        ),
    )
)


class Command(BaseCommand):
    help = (
        "Developer spike: send one text or audio clip to the configured assistant provider and "
        "report the answer, the latency and the tokens. Not for production."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("purpose", choices=["order", "reply", "car", "transcribe"])
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--text", help="An invented message to send.")
        source.add_argument(
            "--audio",
            type=Path,
            help="A test clip (" + ", ".join(sorted(AUDIO_TYPES)) + "), at most 5 MB.",
        )
        parser.add_argument("--locale", choices=["en", "ar"], default="en")
        parser.add_argument(
            "--provider",
            choices=["groq", "gemini", "fake"],
            help="Use this provider instead of AI_PROVIDER (to compare the same input).",
        )
        parser.add_argument(
            "--restaurant",
            help="For 'order': a restaurant slug whose menu is sent (default: an invented menu).",
        )
        parser.add_argument(
            "--repeat",
            type=int,
            default=1,
            help="Repeat the call this many times (1 to 5) to see the latency.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if settings.ENVIRONMENT == "production":
            raise CommandError("The assistant spike never runs in production.")
        repeat = options["repeat"]
        if not 1 <= repeat <= 5:
            raise CommandError("--repeat must be between 1 and 5.")
        message = self._message(options)
        try:
            adapter = get_adapter(options["provider"])
        except ImproperlyConfigured as error:
            raise CommandError(str(error)) from error
        assistant = Assistant(adapter)
        self.stdout.write(
            f"Provider: {adapter.name} · model: {getattr(adapter, 'model', '') or '-'} · "
            f"input: {'audio' if isinstance(message, AudioInput) else 'text'}"
        )
        for number in range(1, repeat + 1):
            self._once(assistant, options, message, number)
        self._summary(repeat)

    def _message(self, options: dict[str, Any]) -> MessageInput:
        if options["text"] is not None:
            return str(options["text"])
        path: Path = options["audio"]
        mime = AUDIO_TYPES.get(path.suffix.lower())
        if mime is None:
            raise CommandError(
                f"Unsupported audio extension {path.suffix!r}. Use one of: "
                + ", ".join(sorted(AUDIO_TYPES))
                + "."
            )
        try:
            data = path.read_bytes()
        except OSError as error:
            raise CommandError(f"Cannot read {path}: {error.strerror}") from error
        if len(data) > limits.MAX_AUDIO_BYTES:
            raise CommandError("The clip is larger than 5 MB.")
        return AudioInput(data=data, mime_type=mime)

    def _menu(self, options: dict[str, Any]) -> PromptMenu:
        slug = options["restaurant"]
        if not slug:
            return SAMPLE_MENU
        restaurant = Restaurant.objects.filter(slug=slug).first()
        if restaurant is None:
            raise CommandError(f"No restaurant with the slug {slug!r}.")
        return build_prompt_menu(restaurant)

    def _once(
        self,
        assistant: Assistant,
        options: dict[str, Any],
        message: MessageInput,
        number: int,
    ) -> None:
        purpose, locale = options["purpose"], options["locale"]
        try:
            if purpose == "order":
                result: Any = assistant.parse_order(
                    self._menu(options), [], None, message, locale
                )
            elif purpose == "reply":
                result = assistant.classify_reply(message, locale)
            elif purpose == "car":
                result = assistant.extract_car_details(
                    CarFields(),
                    ["parking_note", "plate", "model", "colour"],
                    message,
                    locale,
                )
            else:
                if not isinstance(message, AudioInput):
                    raise CommandError("'transcribe' needs --audio.")
                result = assistant.transcribe(message, locale)
        except AssistantInputError as error:
            raise CommandError(str(error)) from error
        except AssistantError as error:
            self.stdout.write(self.style.ERROR(f"#{number} failed: {error.code}"))
            return
        call = AICallLog.objects.order_by("-created_at").first()
        timing = (
            f"{call.latency_ms} ms, tokens in/out: {call.input_tokens}/{call.output_tokens}"
            if call
            else ""
        )
        self.stdout.write(self.style.SUCCESS(f"#{number} ok ({timing})"))
        self.stdout.write(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )

    def _summary(self, repeat: int) -> None:
        calls = list(AICallLog.objects.order_by("-created_at")[:repeat])
        if not calls:
            return
        ok = [c.latency_ms for c in calls if c.outcome == "ok"]
        self.stdout.write(
            f"Done: {len(ok)} of {len(calls)} calls ok"
            + (f", latency {min(ok)} to {max(ok)} ms" if ok else "")
            + ". Accepted audio types: "
            + ", ".join(sorted(limits.ACCEPTED_AUDIO_TYPES))
            + "."
        )
