import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_choice, env_int


class TestEnvBool:
    @pytest.mark.parametrize("value", ["true", "True", " 1 ", "yes", "ON"])
    def test_true_values(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("FLAG", value)

        assert env_bool("FLAG", default=False) is True

    @pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", " off "])
    def test_false_values(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("FLAG", value)

        assert env_bool("FLAG", default=True) is False

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_unset_or_blank_uses_the_default(
        self, monkeypatch: pytest.MonkeyPatch, value: str | None
    ) -> None:
        if value is None:
            monkeypatch.delenv("FLAG", raising=False)
        else:
            monkeypatch.setenv("FLAG", value)

        assert env_bool("FLAG", default=True) is True
        assert env_bool("FLAG", default=False) is False

    def test_a_typo_stops_start_up(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FLAG", "ture")

        with pytest.raises(ImproperlyConfigured, match="FLAG"):
            env_bool("FLAG", default=False)


class TestEnvChoice:
    def test_accepts_a_listed_value_ignoring_case_and_spaces(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MODE", " Enforce ")

        assert env_choice("MODE", "warn", {"off", "warn", "enforce"}) == "enforce"

    def test_unset_uses_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MODE", raising=False)

        assert env_choice("MODE", "warn", {"off", "warn", "enforce"}) == "warn"

    def test_an_unknown_value_stops_start_up_and_lists_the_choices(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MODE", "enfroce")

        with pytest.raises(ImproperlyConfigured, match="enforce, off, warn"):
            env_choice("MODE", "warn", {"off", "warn", "enforce"})


class TestEnvInt:
    def test_reads_a_number(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LIMIT", " 80 ")

        assert env_int("LIMIT", 15) == 80

    def test_unset_uses_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LIMIT", raising=False)

        assert env_int("LIMIT", 15) == 15

    def test_a_non_number_stops_start_up(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LIMIT", "fifteen")

        with pytest.raises(ImproperlyConfigured, match="LIMIT"):
            env_int("LIMIT", 15)

    def test_below_the_minimum_stops_start_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LIMIT", "0")

        with pytest.raises(ImproperlyConfigured, match="at least 1"):
            env_int("LIMIT", 15, minimum=1)

    def test_zero_is_allowed_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LIMIT", "0")

        assert env_int("LIMIT", 15) == 0
