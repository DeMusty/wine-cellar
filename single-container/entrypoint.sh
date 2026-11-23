#!/bin/sh
set -eu

for variable in SECRET_KEY DJANGO_SITE_URL ADMIN_USER ADMIN_USER_EMAIL ADMIN_USER_PASSWORD; do
    if [ -z "$(printenv "$variable" || true)" ]; then
        echo "Missing required environment variable: $variable" >&2
        exit 1
    fi
done
case "$SECRET_KEY:$ADMIN_USER_PASSWORD" in
    *replace-with-*) echo "Set a real secret key and admin password in .env.single." >&2; exit 1 ;;
esac

mkdir -p /data/db /data/media /data/redis /data/beat
python manage.py migrate --noinput
python manage.py shell -c '
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ["ADMIN_USER"]
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, os.environ["ADMIN_USER_EMAIL"], os.environ["ADMIN_USER_PASSWORD"])
'
exec /usr/bin/runsvdir -P /home/app/services
