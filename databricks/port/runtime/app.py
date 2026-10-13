"""Start the pinned application. Startup never imports documents or runs models."""

import os

os.environ["DJANGO_SETTINGS_MODULE"] = "databricks_port.settings"
from databricks_port.startup import initialize  # noqa: E402

initialize()

from databricks_port.transport import start  # noqa: E402

start()
from databricks_port.worker import start as start_worker  # noqa: E402

worker = start_worker()
import uvicorn  # noqa: E402

uvicorn.run(
    "config.asgi:application",
    host="0.0.0.0",
    port=int(os.environ.get("DATABRICKS_APP_PORT", "8000")),
    proxy_headers=True,
)
