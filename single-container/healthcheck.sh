#!/bin/sh
set -eu
for service in redis worker web nginx; do
    /usr/bin/sv check "/home/app/services/$service" >/dev/null
done
/usr/bin/redis-cli -h 127.0.0.1 ping | grep -qx PONG
curl -fsS -H 'Host: localhost' http://127.0.0.1:8080/health/ >/dev/null
