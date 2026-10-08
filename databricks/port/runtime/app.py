"""Start the pinned application. Startup never imports documents or runs models."""

import os

os.environ["DJANGO_SETTINGS_MODULE"] = "databricks_port.settings"
from databricks_port.lakebase import bootstrap  # noqa: E402

bootstrap()

import django  # noqa: E402

django.setup()
from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402

call_command("migrate", interactive=False, verbosity=1)
user, created = get_user_model().objects.get_or_create(username=settings.PILOT_USERNAME)
if created:
    user.is_staff = True
    user.is_superuser = True
    user.is_usage_capped = False
    user.set_unusable_password()
    user.save()

from databricks_port.definitions import install_configured  # noqa: E402

install_configured()

from databricks_port.transport import start  # noqa: E402

start()
import uvicorn  # noqa: E402

uvicorn.run(
    "config.asgi:application",
    host="0.0.0.0",
    port=int(os.environ.get("DATABRICKS_APP_PORT", "8000")),
    proxy_headers=True,
)
