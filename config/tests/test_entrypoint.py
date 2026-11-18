"""The production entrypoint: Gunicorn's default arguments and its access log."""

import os
import shlex
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "entrypoint.prod.sh"


@pytest.fixture
def fake_gunicorn(tmp_path: Path) -> Path:
    """A `gunicorn` that only prints the arguments the entrypoint put in the environment."""
    executable = tmp_path / "gunicorn"
    executable.write_text('#!/usr/bin/env bash\necho "$GUNICORN_CMD_ARGS"\n')
    executable.chmod(executable.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def run_entrypoint(bin_dir: Path, **env: str) -> list[str]:
    environment = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RUN_MIGRATIONS": "false",
        **env,
    }
    result = subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), "gunicorn", "config.wsgi:application"],  # noqa: S607
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return shlex.split(result.stdout.splitlines()[-1])


def test_the_default_arguments_bind_to_the_port(fake_gunicorn: Path) -> None:
    arguments = run_entrypoint(fake_gunicorn, PORT="9123")

    assert "--bind=0.0.0.0:9123" in arguments
    assert "--access-logfile=-" in arguments
    assert "--no-control-socket" in arguments


def test_the_access_log_never_contains_the_query_string(fake_gunicorn: Path) -> None:
    """GET /restaurants/nearby carries the customer's position in its query string."""
    arguments = run_entrypoint(fake_gunicorn)

    [log_format] = [
        a.removeprefix("--access-logformat=")
        for a in arguments
        if a.startswith("--access-logformat=")
    ]
    assert "%(U)s" in log_format  # the path without the query string
    for atom in ("%(r)s", "%(q)s", "%(f)s", "%(a)s"):
        assert atom not in log_format
    assert "%(M)s" in log_format  # the time, in milliseconds
    assert "{x-request-id}o" in log_format  # the id the API sends back


def test_an_explicit_gunicorn_setting_wins(fake_gunicorn: Path) -> None:
    arguments = run_entrypoint(fake_gunicorn, GUNICORN_CMD_ARGS="--workers=3")

    assert arguments == ["--workers=3"]
