import os

from celery import Celery

from wine_cellar.conf.celery_schedule import beat_schedule

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wine_cellar.conf.settings")

celery_app = Celery()
celery_app.config_from_object("django.conf:settings", namespace="CELERY")
celery_app.autodiscover_tasks()

celery_app.conf.beat_schedule = beat_schedule
