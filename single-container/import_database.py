import django

django.setup()

from django.core.management import call_command  # noqa: E402

# Preserve the exported content type and permission IDs instead of recreating them.
call_command("flush", interactive=False, inhibit_post_migrate=True)
call_command("loaddata", "-", format="json")
