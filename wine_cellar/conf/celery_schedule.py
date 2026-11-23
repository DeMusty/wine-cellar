from celery.schedules import crontab

beat_schedule = {
    "drink_by_reminder": {
        "task": "drink_by_reminder",
        "schedule": crontab(minute="30", hour="2"),
    },
    "opened_bottle_reminder": {
        "task": "opened_bottle_reminder",
        "schedule": crontab(minute="30", hour="2"),
    },
}
