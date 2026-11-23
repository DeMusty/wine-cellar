import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("site_url", "host", "origin"),
    [
        ("https://wine.example.com", "wine.example.com", "https://wine.example.com"),
        (
            "https://wine.example.com:8443/",
            "wine.example.com",
            "https://wine.example.com:8443",
        ),
        ("http://localhost:80", "localhost", "http://localhost"),
        ("https://[::1]:8443", "[::1]", "https://[::1]:8443"),
    ],
)
def test_single_settings_derive_hosts_and_origin(site_url, host, origin):
    settings = load_single_settings(site_url)
    assert host in settings["hosts"]
    assert settings["origins"] == [origin]


def test_single_settings_preserve_explicit_overrides():
    settings = load_single_settings(
        "https://wine.example.com",
        DJANGO_ALLOWED_HOSTS="wine.example.com other.example.com",
        DJANGO_CSRF_TRUSTED_ORIGINS="https://other.example.com",
    )
    assert settings["hosts"] == ["wine.example.com", "other.example.com", "localhost"]
    assert settings["origins"] == ["https://other.example.com"]


def test_single_settings_derive_missing_override():
    settings = load_single_settings(
        "https://wine.example.com:8443",
        DJANGO_ALLOWED_HOSTS="other.example.com",
    )
    assert settings["hosts"] == ["other.example.com", "localhost"]
    assert settings["origins"] == ["https://wine.example.com:8443"]


@pytest.mark.parametrize(
    "site_url",
    [
        "",
        "wine.example.com",
        "ftp://wine.example.com",
        "https://user@wine.example.com",
        "https://wine.example.com:invalid",
        "https://wine.example.com\n.evil",
    ],
)
def test_single_settings_reject_invalid_public_urls(site_url):
    result = run_single_settings(site_url)
    assert result.returncode != 0
    assert "DJANGO_SITE_URL must be a valid HTTP(S) URL" in result.stderr


def load_single_settings(site_url, **overrides):
    result = run_single_settings(site_url, **overrides)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def run_single_settings(site_url, **overrides):
    script = textwrap.dedent("""
        import json
        import sys
        import types

        sys.modules["sentry_sdk"] = types.ModuleType("sentry_sdk")
        from django.conf import settings

        print(json.dumps({
            "hosts": settings.ALLOWED_HOSTS,
            "origins": settings.CSRF_TRUSTED_ORIGINS,
        }))
        """)
    env = os.environ.copy()
    env.pop("DJANGO_ALLOWED_HOSTS", None)
    env.pop("DJANGO_CSRF_TRUSTED_ORIGINS", None)
    env.update(
        DJANGO_SETTINGS_MODULE="wine_cellar.conf.single_settings",
        DJANGO_SITE_URL=site_url,
        SECRET_KEY="test-secret",
        SENTRY_DSN="",
        **overrides,
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_sqlite_serializes_concurrent_read_before_write(tmp_path):
    script = textwrap.dedent("""
        import sys
        import threading
        import types

        # Sentry is a production-only dependency and is unused in this test.
        sys.modules["sentry_sdk"] = types.ModuleType("sentry_sdk")

        import django
        from django.conf import settings

        settings.DATABASES["default"]["NAME"] = sys.argv[1]
        django.setup()

        from django.db import connection, connections, transaction

        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE slots (number INTEGER UNIQUE)")

        started = threading.Event()
        finished = threading.Event()
        result = []

        def competing_writer():
            try:
                started.set()
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT COUNT(*) FROM slots WHERE number = 1")
                        result.append(cursor.fetchone()[0])
                        if not result[0]:
                            cursor.execute("INSERT INTO slots VALUES (1)")
            except Exception as exc:
                result.append(exc)
            finally:
                connections.close_all()
                finished.set()

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO slots VALUES (1)")
            thread = threading.Thread(target=competing_writer)
            thread.start()
            assert started.wait(5)
            assert not finished.wait(0.2)

        thread.join(5)
        assert not thread.is_alive()
        assert result == [1], result
        """)
    env = os.environ.copy()
    env.update(
        DJANGO_SETTINGS_MODULE="wine_cellar.conf.single_settings",
        DJANGO_SITE_URL="http://localhost",
        DJANGO_ALLOWED_HOSTS="localhost",
        DJANGO_CSRF_TRUSTED_ORIGINS="http://localhost",
        SECRET_KEY="test-secret",
        SENTRY_DSN="",
    )
    subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "test.sqlite3")],
        env=env,
        check=True,
        timeout=30,
    )


def test_embedded_beat_watchdog_restarts_worker_only_on_failure():
    script = textwrap.dedent("""
        import os
        import signal
        import sys
        import types
        from unittest.mock import Mock, patch

        sys.modules["sentry_sdk"] = types.ModuleType("sentry_sdk")

        from worker import BeatWatchdog

        watchdog = BeatWatchdog(None)
        watchdog.stopping = Mock()
        watchdog.stopping.wait.side_effect = [False, False]
        beat = Mock()
        beat.is_alive.side_effect = [True, False]
        with patch("worker.os.kill") as kill:
            watchdog.watch(beat)
            kill.assert_called_once_with(os.getpid(), signal.SIGTERM)

        watchdog = BeatWatchdog(None)
        watchdog.stopping.set()
        with patch("worker.os.kill") as kill:
            watchdog.watch(beat)
            kill.assert_not_called()
        """)
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(root),
        DJANGO_SETTINGS_MODULE="wine_cellar.conf.single_settings",
        DJANGO_SITE_URL="http://localhost",
        DJANGO_ALLOWED_HOSTS="localhost",
        DJANGO_CSRF_TRUSTED_ORIGINS="http://localhost",
        SECRET_KEY="test-secret",
        SENTRY_DSN="",
    )
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root / "single-container",
        env=env,
        check=True,
        timeout=30,
    )
