# Backups

It is recommended to make periodic backups and ideally also before major version upgrades.

## Single-container SQLite

These instructions apply to `docker-compose.single.yml`, not the PostgreSQL
deployment described below. Stop the container first so the database, uploads,
Redis data and beat schedule are consistent. Do not copy a live SQLite database
file on its own.

```sh
docker compose -f docker-compose.single.yml stop
docker compose -f docker-compose.single.yml cp -a wine-cellar:/data - > wine-cellar-backup.tar
docker compose -f docker-compose.single.yml start
```

Keep the archive securely and separately retain your `.env.single` and secret
key. Redis data can contain queued task payloads.

To restore, stop the original deployment and extract the archive into a **new
empty Docker volume**. Choose a volume name that does not already exist. For
example:

```sh
docker compose -f docker-compose.single.yml stop
docker volume create wine-cellar-restore
docker run --rm -i --user 0:0 --entrypoint tar -v wine-cellar-restore:/data \
  wine-cellar-single:local -xpf - -C / < wine-cellar-backup.tar
```

Then create a Compose override that points `wine_cellar_data` at the restored
external volume:

```yaml
volumes:
  wine_cellar_data:
    external: true
    name: wine-cellar-restore
```

Start with `docker compose -f docker-compose.single.yml -f <override-file> up -d`.
Keep the original volume until the restored instance has been checked. Ensure
the restored file ownership allows the image's `app` user to write to `/data`.
Do not run both instances against the same volume.

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