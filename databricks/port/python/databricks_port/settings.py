"""Deployment-only settings; stock model/context and workflow logic remain upstream."""

import os
from urllib.parse import urlparse

os.environ.setdefault("DATABASE_URL", "postgres://localhost/databricks_postgres")
os.environ.setdefault("DJANGO_READ_DOT_ENV_FILE", "false")
from config.settings.base import *  # noqa: E402,F403

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
APP_ORIGIN = os.environ["APP_ORIGIN"].rstrip("/")
PILOT_USERNAME = os.environ["PILOT_USERNAME"]
DATABASES["default"].update(  # noqa: F405
    ENGINE="databricks_port.db", ATOMIC_REQUESTS=False, CONN_MAX_AGE=0
)
ROOT_URLCONF = "databricks_port.urls"
ADMIN_URL = "django-admin/"
MIDDLEWARE.insert(  # noqa: F405
    0, "databricks_port.token_transport.BackendTokenHeaderMiddleware"
)  # noqa: F405
ALLOWED_HOSTS = ["localhost", "127.0.0.1", urlparse(APP_ORIGIN).hostname]
CSRF_TRUSTED_ORIGINS = [APP_ORIGIN]
CORS_ALLOWED_ORIGINS = [APP_ORIGIN]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CSP_DIRECTIVES["connect-src"] = list(  # noqa: F405
    SECURE_CSP_DIRECTIVES["connect-src"]  # noqa: F405
) + [  # noqa: F405
    "blob:"
]
USE_AUTH0 = False
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
# Initial bounded owner-operated runtime. Durable asynchronous recovery is a
# separate acceptance item; eager execution is not advertised as a durable queue.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache"
CELERY_CACHE_BACKEND = "memory"
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STORAGES = {
    "default": {"BACKEND": "databricks_port.storage.LakebaseStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
DEFAULT_EMBEDDER = (
    "opencontractserver.pipeline.embedders.databricks_embedder.DatabricksEmbedder"
)
PREFERRED_EMBEDDERS = {"application/pdf": DEFAULT_EMBEDDER}
PREFERRED_PARSERS = {
    "application/pdf": "opencontractserver.pipeline.parsers.warp_local_parser.WarpLocalParser"
}
DEFAULT_EMBEDDING_DIMENSION = int(os.environ["EMBEDDING_DIMENSIONS"])
DEFAULT_LLM = "openai:" + os.environ["EXTRACTION_MODEL_ENDPOINT"]
OPENAI_MODEL = os.environ["EXTRACTION_MODEL_ENDPOINT"]
OPENAI_API_KEY = "app-oauth-loopback"
OPENAI_API_BASE_URL = "http://127.0.0.1:9001/v1"
EMBEDDING_MODEL_ENDPOINT = os.environ["EMBEDDING_MODEL_ENDPOINT"]
EMBEDDING_DIMENSIONS = int(os.environ["EMBEDDING_DIMENSIONS"])
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
os.environ["OPENAI_BASE_URL"] = OPENAI_API_BASE_URL
MODE = "DATABRICKS_PILOT"
