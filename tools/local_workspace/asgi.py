"""Serve the complete local workspace beneath one bridge path.

The listener binds only to loopback. Remote use requires the existing authenticated
Azure/Tailscale gateway. The browser receives the native application JWT for the
installation's single owner; neither provider keys nor owner passwords are served.
"""

import json
import mimetypes
import os
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.workspace")

from asgiref.sync import sync_to_async  # noqa: E402
from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402

from config.asgi import application as backend  # noqa: E402
from config.jwt_auth.shortcuts import get_token  # noqa: E402

PREFIX = getattr(settings, "APP_BASE_PATH", "/opencontracts")
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"


async def respond(send, status, body, content_type):
    if isinstance(body, str):
        body = body.encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", content_type.encode()),
                (b"cache-control", b"no-store"),
                (b"x-content-type-options", b"nosniff"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


@sync_to_async
def owner_token():
    user = get_user_model().objects.get(
        username=os.environ["LOCAL_OWNER_USERNAME"], is_active=True
    )
    return get_token(user)


async def application(scope, receive, send):
    path = scope.get("path", "")
    api = PREFIX + "/__api"
    if path.startswith(api + "/"):
        child = {**scope, "path": path[len(api) :], "root_path": ""}
        if "raw_path" in child:
            child["raw_path"] = child["path"].encode()
        if scope["type"] == "http":
            origins = [
                value.decode()
                for name, value in scope.get("headers", [])
                if name.lower() == b"origin"
            ]
            allowed_origins = {
                getattr(settings, "APP_PUBLIC_ORIGIN", "http://127.0.0.1:4400"),
                "http://127.0.0.1:4400",
                "http://localhost:4400",
            }
            if origins and (len(origins) != 1 or origins[0] not in allowed_origins):
                return await respond(
                    send, 403, "Unexpected browser origin.", "text/plain"
                )
            # Azure's gateway strips browser Authorization/cookies. The trusted
            # loopback adapter supplies its own single-owner application token;
            # no client identity header or Microsoft bearer token is trusted.
            child["headers"] = [
                (name, value)
                for name, value in scope.get("headers", [])
                if name.lower() not in {b"authorization", b"cookie"}
            ] + [(b"authorization", ("Bearer " + await owner_token()).encode())]
        if child["path"].startswith("/media/") and scope["type"] == "http":
            media_root = Path(settings.MEDIA_ROOT).resolve()
            file = (media_root / child["path"][len("/media/") :]).resolve()
            if not file.is_relative_to(media_root) or not file.is_file():
                return await respond(send, 404, "Not found", "text/plain")
            return await respond(
                send,
                200,
                file.read_bytes(),
                mimetypes.guess_type(file.name)[0] or "application/octet-stream",
            )
        return await backend(child, receive, send)
    if scope["type"] != "http":
        return await send({"type": "websocket.close", "code": 1008})
    if not (path == PREFIX or path.startswith(PREFIX + "/")):
        return await respond(send, 404, "Not found", "text/plain")
    if scope["method"] not in {"GET", "HEAD"}:
        return await respond(send, 405, "Method not allowed", "text/plain")
    if path == PREFIX + "/__session":
        return await respond(
            send, 200, json.dumps({"token": await owner_token()}), "application/json"
        )
    if path == PREFIX + "/env-config.js":
        env = {
            "REACT_APP_API_ROOT_URL": api,
            "REACT_APP_BASE_PATH": PREFIX,
            "REACT_APP_USE_AUTH0": False,
            "REACT_APP_USE_ANALYZERS": True,
            "REACT_APP_ALLOW_IMPORTS": True,
        }
        # This classic script runs before the module entry. AuthGate reads the
        # normal native-session format; the password never enters browser code.
        script = (
            "window._env_="
            + json.dumps(env)
            + ";window._env_.REACT_APP_API_ROOT_URL=location.origin+"
            + json.dumps(api)
            + ";\n"
        )
        script += (
            "window.__workspaceReady=fetch("
            + json.dumps(PREFIX + "/__session")
            + ", {cache:'no-store'}).then(r=>{"
            + "if(!r.ok)throw Error('Sign-in unavailable');return r.json()})"
            + ".then(({token})=>sessionStorage.setItem('oc_local_auth_session',"
            + "JSON.stringify({token,api:location.origin+"
            + json.dumps(api)
            + ",expiresAt:Date.now()+3600000})));"
        )
        return await respond(send, 200, script, "text/javascript")
    relative = path[len(PREFIX) :].lstrip("/") or "index.html"
    file = (FRONTEND / relative).resolve()
    if not file.is_relative_to(FRONTEND.resolve()):
        return await respond(send, 404, "Not found", "text/plain")
    if not file.is_file():
        if "." in Path(relative).name:
            return await respond(send, 404, "Not found", "text/plain")
        file = FRONTEND / "index.html"
    if not file.is_file():
        return await respond(send, 503, "Build the frontend first.", "text/plain")
    return await respond(
        send,
        200,
        file.read_bytes(),
        mimetypes.guess_type(file.name)[0] or "application/octet-stream",
    )
