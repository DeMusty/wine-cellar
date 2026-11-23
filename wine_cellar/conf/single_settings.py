import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from django.http.request import split_domain_port


def _configure_public_url():
    site_url = os.environ.get("DJANGO_SITE_URL", "")
    try:
        parsed = urlsplit(site_url)
        host, port = split_domain_port(parsed.netloc)
        port_number = parsed.port
    except ValueError as exc:
        raise ImproperlyConfigured(
            "DJANGO_SITE_URL must be a valid HTTP(S) URL"
        ) from exc

    if (
        not site_url
        or any(char.isspace() or ord(char) < 32 for char in site_url)
        or parsed.scheme not in ("http", "https")
        or not host
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ImproperlyConfigured("DJANGO_SITE_URL must be a valid HTTP(S) URL")

    origin_host = parsed.netloc.lower()
    if port:
        origin_host = origin_host[: -(len(port) + 1)]
        if port_number != {"http": 80, "https": 443}[parsed.scheme]:
            origin_host += f":{port_number}"
    origin = f"{parsed.scheme}://{origin_host}"
    # docker_settings reads these variables while it is imported below.
    if not os.environ.get("DJANGO_ALLOWED_HOSTS"):
        os.environ["DJANGO_ALLOWED_HOSTS"] = host
    if not os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS"):
        os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = origin


_configure_public_url()

from wine_cellar.conf.docker_settings import *  # noqa: E402, F403, F401

ALLOWED_HOSTS += ["localhost"]  # noqa: F405
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/data/db/wine-cellar.sqlite3",
        "OPTIONS": {
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
        },
    }
}
MEDIA_ROOT = "/data/media"
CELERY_BROKER_URL = "redis://127.0.0.1:6379"
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
for cache in ("wine_prefill", "whats_new"):
    CACHES[cache]["LOCATION"] = f"{CELERY_BROKER_URL}/1"  # noqa: F405
