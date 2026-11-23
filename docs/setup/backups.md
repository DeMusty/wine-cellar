# Backups

It is recommended to make periodic backups and ideally also before major version upgrades.

## Migration to the single container

The production or development PostgreSQL Compose deployment can be exported
and imported into a **new, empty** single-container data directory. This copies all
Django database records and uploaded media; the backup also contains a
PostgreSQL SQL dump for restoring the original deployment. Redis queues, cached
results and the beat schedule are not transferred. Finish or discard queued
jobs before stopping the source.

Use the same Wine Cellar release for the source web image and the single image,
and ensure the source database has no unapplied migrations. The importer checks
the application version and migration plan; it cannot detect different builds
with the same version. Both deployments must be run from the project directory
with their normal Compose configuration and environment files. If moving to a
different host, securely transfer the backup directory to that host.

1. Stop all source application writers, leaving PostgreSQL running. Prevent
   other clients from writing to the database or media until the export is
   complete.

   === "Production"
       ```sh
       docker compose -f docker-compose.prod.yml stop caddy web celery celery-beat
       docker compose -f docker-compose.prod.yml up -d db
       sh scripts/migrate-to-single.sh export ../wine-cellar-migration-backup
       ```

   === "Development"
       ```sh
       docker compose -f docker-compose.yml stop web celery celery-beat
       docker compose -f docker-compose.yml up -d db
       sh scripts/migrate-to-single.sh export --dev ../wine-cellar-migration-backup
       ```

       Development media is read from the `mediafiles/` directory in the project
       bind mount. If that directory does not exist, the backup contains no media.

   The backup directory must not already exist. Keep it outside the repository:
   it contains sensitive account data, password hashes and possibly tokens.
   Protect it and retain it securely.
   The original database and media volumes are not changed. If exporting fails,
   discard the incomplete directory or choose a new name before retrying.

2. Configure `.env.single` using the existing `SECRET_KEY` and other settings
   from the original deployment. Set `ADMIN_USER` to an existing administrator's
   username to avoid creating an additional administrator on startup. Build the
   matching single-container image without starting the service. If your
   development secret is the public value from `.env.dev-sample`, use a new
   random secret instead; existing sessions and signed tokens will be invalidated.
   Change any default development passwords before exposing the new deployment.

   ```sh
   docker compose -f docker-compose.single.yml stop
   docker compose -f docker-compose.single.yml build
   mkdir -p ./data/single-container
   docker compose -f docker-compose.single.yml run --rm --no-deps --user 0:0 \
     --entrypoint sh wine-cellar -c '
       if [ -n "$(find /data -mindepth 1 -print -quit)" ]; then
         echo "Data directory is not empty; refusing to prepare it." >&2
         exit 1
       fi
       chown app:app /data && chmod 700 /data
     '
   sh scripts/migrate-to-single.sh import ../wine-cellar-migration-backup
   docker compose -f docker-compose.single.yml up -d
   ```

   The import refuses a running single-container service or a data directory
   containing files. If an import fails after preparing the database, use a new
   empty `data/single-container` directory before retrying; do not remove
   existing data without first confirming its contents. Import only backups
   you trust.

3. Check users, wine inventory, history and uploaded images in the new
   deployment before switching your reverse proxy to it. Keep the original
   deployment stopped and its volumes and backup intact until verification is
   complete. Once the new deployment accepts writes, restarting the old one
   will not include those changes.

## Single-container SQLite

These instructions apply to `docker-compose.single.yml`, not the PostgreSQL
deployment described below. The data is in `./data/single-container`. Stop the
container first so the database, uploads, Redis data and beat schedule are
consistent. Do not copy a live SQLite database file on its own.

```sh
docker compose -f docker-compose.single.yml stop
docker compose -f docker-compose.single.yml run --rm --no-deps --user 0:0 \
  --entrypoint tar wine-cellar -cpf - -C /data . > ../wine-cellar-backup.tar
docker compose -f docker-compose.single.yml start
```

Keep the archive securely and separately retain your `.env.single` and secret
key. Redis data can contain queued task payloads.

To restore, stop the deployment and use a **new, empty** `data/single-container`
directory. Preserve the existing directory separately; do not overwrite it.
Restore only a trusted archive:

```sh
docker compose -f docker-compose.single.yml stop
docker compose -f docker-compose.single.yml run --rm --no-deps --user 0:0 \
  --entrypoint sh wine-cellar -c '
    set -eu
    if [ -n "$(find /data -mindepth 1 -print -quit)" ]; then
      echo "Data directory is not empty; refusing to restore." >&2
      exit 1
    fi
    tar -xpf - -C /data
    chown app:app /data
    chmod 700 /data
  ' < ../wine-cellar-backup.tar
docker compose -f docker-compose.single.yml up -d
```

Keep the original data until the restored instance has been checked. Ensure
the restored file ownership allows the image's `app` user to write to `/data`.
Do not run both instances against the same directory.

### Moving an existing single-container volume

The bind mount does not automatically copy data from the earlier named volume.
Before starting the new configuration, stop the old container and ensure no
other container is using its volume. Find the old volume with `docker volume ls`
and replace `<old-volume-name>` below with its exact name. The destination must
be empty; the command refuses to overwrite existing files.

```sh
docker compose -f docker-compose.single.yml stop
docker compose -f docker-compose.single.yml build
mkdir -p ./data/single-container
docker run --rm --user 0:0 --entrypoint sh \
  -v <old-volume-name>:/old:ro -v "$PWD/data/single-container:/new" \
  wine-cellar-single:local -c '
    set -eu
    if [ -n "$(find /new -mindepth 1 -print -quit)" ]; then
      echo "Data directory is not empty; refusing to copy." >&2
      exit 1
    fi
    cp -a /old/. /new/
    chown app:app /new
    chmod 700 /new
  '
docker compose -f docker-compose.single.yml up -d
```

Verify the new deployment before removing the old volume. If the copy fails,
inspect and preserve the partially copied directory before retrying.

## Backup

### Database Backup
To create a backup of your database you can run the following command

???+ Info 
    Either the whole compose or at least the `db` container must be up and running to be able to use `exec`.

=== "Docker"
    ```sh
    docker compose -f docker-compose.prod.yml exec db pg_dump -U django -d django > wine-cellar-postgres-backup-$(date +%F).sql
    ```

=== "Podman"
    ```sh
    podman-compose -f docker-compose.prod.yml exec db pg_dump -U django -d django > wine-cellar-postgres-backup-$(date +%F).sql
    ```



### Media Backup
To backup the user uploaded media the easiest way is to just make a backup or copy of the volume. In a default configuration the
path should be

=== "Docker"
    ```sh
    /var/lib/docker/volumes/wine-cellar_media_volume/_data
    ```

=== "Podman"
    ```sh
    /var/lib/containers/storage/volumes/wine-cellar_media_volume/_data/
    ```

If that path doesn't exist you can use the `inspect` command to find the correct one:

=== "Docker"
    ```sh
    docker volume inspect wine-cellar_media_volume      
    ```

=== "Podman"
    ```sh
    podman volume inspect wine-cellar_media_volume      
    ```

## Restore

Before attempting to restore make sure your database backup is valid. To do so open the `sql` file and check that it starts with something similar to:

```sql
--
-- PostgreSQL database dump
--

-- Dumped from database version 16.11 (Debian 16.11-1.pgdg13+1)
-- Dumped by pg_dump version 16.11 (Debian 16.11-1.pgdg13+1)
```

### Restore Database

#### Stop Containers
We only want the db container to run for this step.

=== "Docker"
    ```sh
    docker compose -f docker-compose.prod.yml down
    docker compose -f docker-compose.prod.yml up -d db
    ```

=== "Podman"
    ```sh
    podman-compose -f docker-compose.prod.yml down 
    podman-compose -f docker-compose.prod.yml up -d db
    ```

#### Recreate empty database

=== "Docker"
    ```sh
    docker compose -f docker-compose.prod.yml exec db psql -U django -d postgres -c "DROP DATABASE django;"
    docker compose -f docker-compose.prod.yml exec db psql -U django -d postgres -c "CREATE DATABASE django;"
    ```

=== "Podman"
    ```sh
    podman-compose -f docker-compose.prod.yml exec db psql -U django -d postgres -c "DROP DATABASE django;"
    podman-compose -f docker-compose.prod.yml exec db psql -U django -d postgres -c "CREATE DATABASE django;"
    ```

#### Restore database

=== "Docker"
    ```sh
    docker compose -f docker-compose.prod.yml exec -T db psql -U django -d django < wine-cellar-postgres-backup-<date>.sql
    ```

=== "Podman"
    ```sh
    podman-compose -f docker-compose.prod.yml exec -T db psql -U django -d django < wine-cellar-postgres-backup-<date>.sql
    ```

### Restore Media Folder
Copy the backup of the media folder to the media volume. Make sure the folder has the correct permissions.

### Restart

=== "Docker"
    ```sh
    docker compose -f docker-compose.prod.yml down
    docker compose -f docker-compose.prod.yml up -d
    ```

=== "Podman"
    ```sh
    podman-compose -f docker-compose.prod.yml down 
    podman-compose -f docker-compose.prod.yml up -d
    ```