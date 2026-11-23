#!/bin/sh
set -eu
umask 077

usage() {
    echo "Usage: sh scripts/migrate-to-single.sh export [--dev] BACKUP_DIRECTORY" >&2
    echo "       sh scripts/migrate-to-single.sh import BACKUP_DIRECTORY" >&2
    exit 1
}

source_file=docker-compose.prod.yml
media_dir=/home/app/web/mediafiles
allow_missing_media=no
if [ "$#" -eq 3 ] && [ "$1" = export ] && [ "$2" = --dev ]; then
    source_file=docker-compose.yml
    media_dir=/usr/src/app/mediafiles
    allow_missing_media=yes
    set -- "$1" "$3"
fi
[ "$#" -eq 2 ] || usage
action=$1
backup=$2
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
cd "$root"

source_compose() {
    docker compose -f "$source_file" "$@"
}

target_compose() {
    docker compose -f docker-compose.single.yml "$@"
}

case "$action" in
    export)
        running=$(source_compose ps --status running --services)
        if printf '%s\n' "$running" | grep -Eq '^(web|celery|celery-beat)$'; then
            echo "Stop the source web, celery and celery-beat services before exporting." >&2
            exit 1
        fi
        if ! printf '%s\n' "$running" | grep -qx db; then
            echo "The source db service must be running." >&2
            exit 1
        fi
        if ! mkdir "$backup"; then
            echo "Backup directory must be new and its parent must exist: $backup" >&2
            exit 1
        fi
        backup=$(CDPATH= cd -- "$backup" && pwd -P)
        echo "Exporting database and media to $backup..."
        source_compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$backup/postgres.sql"
        source_compose run --rm --no-deps -T --entrypoint python web -c 'from wine_cellar import __version__; print(__version__)' > "$backup/version.txt"
        source_compose run --rm --no-deps -T --entrypoint python web manage.py showmigrations --plan --no-color > "$backup/migrations.txt"
        if grep -q '\[ \]' "$backup/migrations.txt"; then
            echo "Source has unapplied migrations. Apply them before exporting." >&2
            exit 1
        fi
        source_compose run --rm --no-deps -T --entrypoint python web manage.py dumpdata --all --no-color > "$backup/data.json"
        source_compose run --rm --no-deps -T --entrypoint sh web -c '
            if [ -d "$1" ]; then
                exec tar -cf - -C "$1" .
            elif [ "$2" = yes ] && [ ! -e "$1" ] && [ ! -L "$1" ]; then
                echo "Media directory does not exist: $1; creating an empty archive." >&2
                exec tar -cf - --files-from /dev/null
            else
                echo "Media path is not a directory: $1" >&2
                exit 1
            fi
        ' sh "$media_dir" "$allow_missing_media" > "$backup/media.tar"
        echo "Backup complete. Keep it private; it contains passwords and application data."
        ;;
    import)
        for file in postgres.sql version.txt migrations.txt data.json media.tar; do
            if [ ! -s "$backup/$file" ]; then
                echo "Missing or empty backup file: $backup/$file" >&2
                exit 1
            fi
        done
        backup=$(CDPATH= cd -- "$backup" && pwd -P)
        running=$(target_compose ps --status running --services)
        if printf '%s\n' "$running" | grep -qx wine-cellar; then
            echo "Stop the single-container service before importing." >&2
            exit 1
        fi
        target_compose run --rm --no-deps -T init-data
        target_compose run --rm --no-deps -T --entrypoint sh wine-cellar -c '
            if [ -n "$(find /data -mindepth 1 ! -type d -print -quit)" ]; then
                echo "Target /data is not empty. Use a new empty directory." >&2
                exit 1
            fi
            mkdir -p /data/db /data/media /data/redis /data/beat
            python manage.py migrate --noinput
        '
        target_plan=$(mktemp)
        trap 'rm -f "$target_plan"' EXIT
        target_compose run --rm --no-deps -T --entrypoint python wine-cellar -c 'from wine_cellar import __version__; print(__version__)' > "$target_plan"
        if ! cmp -s "$backup/version.txt" "$target_plan"; then
            echo "Source and target versions differ. Use matching application versions." >&2
            exit 1
        fi
        target_compose run --rm --no-deps -T --entrypoint python wine-cellar manage.py showmigrations --plan --no-color > "$target_plan"
        if ! cmp -s "$backup/migrations.txt" "$target_plan"; then
            echo "Source and target migrations differ. Use matching application versions." >&2
            exit 1
        fi
        target_compose run --rm --no-deps -T --entrypoint python wine-cellar -c 'exec(open("/home/app/single-container/import_database.py").read())' < "$backup/data.json"
        target_compose run --rm --no-deps -T --entrypoint tar wine-cellar -xf - -C /data/media < "$backup/media.tar"
        echo "Import complete. Start the single container and verify your data."
        ;;
    *)
        usage
        ;;
esac
