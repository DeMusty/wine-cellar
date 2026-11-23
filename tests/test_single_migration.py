import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_python(database, *args, input=None):
    env = os.environ.copy()
    env.update(
        DJANGO_SETTINGS_MODULE="wine_cellar.conf.test",
        SQL_ENGINE="django.db.backends.sqlite3",
        SQL_DATABASE=str(database),
    )
    command = [sys.executable, *args]
    if args[0] == "manage.py" and args[1] != "shell":
        command.append("--skip-checks")
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        input=input,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result


def test_fixture_import_preserves_data_and_does_not_run_creation_signals(tmp_path):
    source = tmp_path / "source.sqlite3"
    target = tmp_path / "target.sqlite3"
    for db in (source, target):
        run_python(db, "manage.py", "migrate", "--noinput", "--verbosity", "0")

    run_python(
        source,
        "manage.py",
        "shell",
        "-c",
        """
from django.contrib.auth.models import Group, Permission, User
from wine_cellar.apps.storage.models import Storage
from wine_cellar.apps.wine.models import Vintage, Wine, WineImage
user = User.objects.create_user(username="imported", password="secret")
Storage.objects.filter(user=user).delete()
Storage.objects.create(user=user, name="Custom", location="Cellar")
group = Group.objects.create(name="custom")
group.permissions.add(Permission.objects.first())
user.groups.add(group)
wine = Wine.objects.create(user=user, name="Example", wine_type="RE", country="FR")
vintage = Vintage.objects.create(user=user, wine=wine)
image = WineImage.objects.create(vintage=vintage)
WineImage.objects.filter(pk=image.pk).update(image="missing.jpg")
""",
    )
    fixture = run_python(source, "manage.py", "dumpdata", "--all").stdout
    run_python(
        target,
        "-c",
        'exec(open("single-container/import_database.py").read())',
        input=fixture,
    )
    restored = run_python(target, "manage.py", "dumpdata", "--all").stdout

    def sort_key(obj):
        return obj["model"], str(obj["pk"])

    assert sorted(json.loads(fixture), key=sort_key) == sorted(
        json.loads(restored), key=sort_key
    )


@pytest.mark.parametrize(
    ("options", "compose_file", "media_path", "allow_missing"),
    [
        ([], "docker-compose.prod.yml", "/home/app/web/mediafiles", "no"),
        (["--dev"], "docker-compose.yml", "/usr/src/app/mediafiles", "yes"),
    ],
)
def test_export_selects_source_and_media(
    tmp_path, options, compose_file, media_path, allow_missing
):
    log = tmp_path / "docker.log"
    docker = tmp_path / "docker"
    docker.write_text("""#!/bin/sh
printf '%s\\n' "$*" >> "$DOCKER_LOG"
case "$*" in
    *"ps --status running --services"*) echo db ;;
    *showmigrations*) echo '[X] wine.0001_initial' ;;
    *dumpdata*) echo '[]' ;;
    *) echo test ;;
esac
""")
    docker.chmod(0o755)
    env = os.environ.copy()
    env.update(PATH=f"{tmp_path}{os.pathsep}{env['PATH']}", DOCKER_LOG=str(log))
    result = subprocess.run(
        [
            "sh",
            str(ROOT / "scripts/migrate-to-single.sh"),
            "export",
            *options,
            str(tmp_path / "backup"),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = log.read_text()
    assert calls.count(f"compose -f {compose_file} ") == 6
    assert f"sh {media_path} {allow_missing}" in calls


def test_dev_export_refuses_running_writers(tmp_path):
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\nprintf 'db\\nweb\\n'\n")
    docker.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    backup = tmp_path / "backup"
    result = subprocess.run(
        [
            "sh",
            str(ROOT / "scripts/migrate-to-single.sh"),
            "export",
            "--dev",
            str(backup),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Stop the source" in result.stderr
    assert not backup.exists()


def test_import_initializes_data_directory_before_using_it(tmp_path):
    log = tmp_path / "docker.log"
    docker = tmp_path / "docker"
    docker.write_text("""#!/bin/sh
printf '%s\\n' "$*" >> "$DOCKER_LOG"
case "$*" in
    *"ps --status running --services"*) ;;
    *) echo test ;;
esac
""")
    docker.chmod(0o755)
    backup = tmp_path / "backup"
    backup.mkdir()
    for filename in ("postgres.sql", "version.txt", "migrations.txt", "media.tar"):
        (backup / filename).write_text("test\n")
    (backup / "data.json").write_text("[]")
    env = os.environ.copy()
    env.update(PATH=f"{tmp_path}{os.pathsep}{env['PATH']}", DOCKER_LOG=str(log))
    result = subprocess.run(
        ["sh", str(ROOT / "scripts/migrate-to-single.sh"), "import", str(backup)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = log.read_text()
    assert calls.index("run --rm --no-deps -T init-data") < calls.index(
        "run --rm --no-deps -T --entrypoint sh wine-cellar"
    )
