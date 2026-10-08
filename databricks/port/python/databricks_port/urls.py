"""Same-origin hosting for stock OpenContracts behind the Databricks Apps boundary."""

import json
import mimetypes
import time
from pathlib import Path

from databricks_port.docling_corpus import DoclingCorpusCopy, DoclingCorpusStatus
from databricks_port.token_transport import TOKEN_TRANSPORT_SCRIPT
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.urls import path, re_path

from config.jwt_auth.shortcuts import get_token
from config.urls import urlpatterns as stock_urls

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def runtime_env(request):
    env = {
        "REACT_APP_API_ROOT_URL": settings.APP_ORIGIN,
        "REACT_APP_USE_AUTH0": "false",
    }
    return HttpResponse(
        "window._env_=" + json.dumps(env) + ";", content_type="application/javascript"
    )


def session_state():
    user = get_user_model().objects.get(username=settings.PILOT_USERNAME)
    duration = settings.GRAPHQL_JWT["JWT_EXPIRATION_DELTA"].total_seconds()
    # The stock browser accepts a local session envelope for at most 24 hours,
    # independently of the JWT's stock lifetime. Allow a clock margin.
    duration = min(duration, 24 * 60 * 60 - 60)
    return {
        "token": get_token(user),
        "api": settings.APP_ORIGIN,
        "expiresAt": int((time.time() + duration) * 1000),
    }


def session(request):
    response = JsonResponse(session_state())
    response["Cache-Control"] = "no-store"
    return response


def transport_js(request):
    return HttpResponse(TOKEN_TRANSPORT_SCRIPT, content_type="application/javascript")


def installation_status(request):
    """Aggregate startup/emptiness checks behind the Databricks App boundary."""
    from opencontractserver.annotations.models import LabelSet
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document, PipelineSettings
    from opencontractserver.extracts.models import Datacell, Extract, Fieldset

    user = get_user_model().objects.get(username=settings.PILOT_USERNAME)
    response = JsonResponse(
        {
            "counts": {
                "documents": Document.objects.count(),
                "corpora": Corpus.objects.count(),
                "extracts": Extract.objects.count(),
                "datacells": Datacell.objects.count(),
                "fieldsets": Fieldset.objects.count(),
                "labelsets": LabelSet.objects.count(),
            },
            "owner_usage_capped": user.is_usage_capped,
            "pdf_parser": PipelineSettings.get_instance().preferred_parsers.get(
                "application/pdf"
            ),
        }
    )
    response["Cache-Control"] = "no-store"
    return response


def media(request, name):
    from databricks_port.storage import LakebaseStorage

    try:
        file = LakebaseStorage().open(name)
    except FileNotFoundError:
        raise Http404
    return FileResponse(
        file, content_type=mimetypes.guess_type(name)[0] or "application/octet-stream"
    )


def frontend(request, asset=""):
    target = (DIST / asset).resolve()
    if not target.is_relative_to(DIST.resolve()):
        raise Http404
    if target.is_file():
        return FileResponse(
            target.open("rb"),
            content_type=mimetypes.guess_type(str(target))[0]
            or "application/octet-stream",
        )
    # Leave route interpretation to the stock React router. Missing bundle
    # assets must not become a successful response containing the SPA shell.
    if asset.split("/", 1)[0] in {"assets", "docxodus-wasm"}:
        raise Http404
    html = (DIST / "index.html").read_text()
    state = json.dumps(session_state()).replace("<", "\\u003c")
    scripts = (
        '<script nonce="'
        + request.csp_nonce
        + '">sessionStorage.setItem("oc_local_auth_session",JSON.stringify('
        + state
        + '));</script><script src="/port/transport.js"></script>'
    )
    html = html.replace(
        '<script src="/env-config.js"></script>',
        '<script src="/env-config.js"></script>' + scripts,
    )
    response = HttpResponse(html)
    response["Cache-Control"] = "no-store"
    return response


urlpatterns = (
    [
        path("env-config.js", runtime_env),
        path("port/session", session),
        path("port/transport.js", transport_js),
        path("port/installation-status", installation_status),
        path("port/docling/corpora", DoclingCorpusCopy.as_view()),
        path("port/docling/corpora/<int:corpus_id>", DoclingCorpusStatus.as_view()),
        path("port/media/<path:name>", media),
    ]
    + [
        (
            path(
                (
                    "django-admin/login/"
                    if route.name == "admin_auth0_login"
                    else "django-admin/logout/"
                ),
                route.callback,
                route.default_args,
                name=route.name,
            )
            if getattr(route, "name", None)
            in {"admin_auth0_login", "admin_auth0_logout"}
            else route
        )
        for route in stock_urls
        if getattr(route, "name", None) != "home_redirect"
    ]
    + [re_path(r"^(?P<asset>.*)$", frontend)]
)
