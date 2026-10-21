"""Persistent single-user local application behind an authenticated bridge."""

import os
from pathlib import Path
from urllib.parse import urlparse

from .base import *  # noqa: F403

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
USE_AUTH0 = False
APP_PUBLIC_ORIGIN = os.environ.get("APP_PUBLIC_ORIGIN", "http://127.0.0.1:4400")
APP_BASE_PATH = os.environ.get("APP_BASE_PATH", "/opencontracts").rstrip("/")
ALLOWED_HOSTS = ["127.0.0.1", "localhost", urlparse(APP_PUBLIC_ORIGIN).hostname]
CSRF_TRUSTED_ORIGINS = [APP_PUBLIC_ORIGIN]
CORS_ALLOWED_ORIGINS = [APP_PUBLIC_ORIGIN]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DATABASES["default"]["ATOMIC_REQUESTS"] = False  # noqa: F405
MEDIA_ROOT = str(Path(os.environ["LOCAL_WORKSPACE_STATE"]) / "media")
MEDIA_URL = APP_BASE_PATH + "/__api/media/"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_EMBEDDER = (
    "opencontractserver.pipeline.embedders.openai_embedder.OpenAIEmbedder"
)
PREFERRED_EMBEDDERS = {
    "application/pdf": DEFAULT_EMBEDDER,
    "text/plain": DEFAULT_EMBEDDER,
}
DEFAULT_EMBEDDING_DIMENSION = 1536
PREFERRED_PARSERS = {
    **PREFERRED_PARSERS,  # noqa: F405
    "application/pdf": "opencontractserver.pipeline.parsers.warp_ingest_parser.WarpIngestParser",
}  # noqa: F405
DEFAULT_LLM = os.environ.get("DEFAULT_LLM", "openai:gpt-6-luna")
AUTO_CREATE_PERSONAL_CORPUS = False
CORPUS_AUTO_BRANDING_ENABLED = False
CORPUS_LOGO_GENERATION_ENABLED = False
CELERY_WORKER_CONCURRENCY = 1
CELERY_TASK_ROUTES = {}
