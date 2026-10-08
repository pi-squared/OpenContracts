"""Loopback OpenAI API adapter; preserve stock requests and refresh app OAuth."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

import requests
from databricks_port import lakebase


def normalize_chat_content(body):
    """Adapt Databricks typed assistant content to the native OpenAI contract.

    Preserve tool calls and keep reasoning separate from answer text. Ordinary
    Chat Completions bodies pass through byte-for-byte. The experiment's wire
    audit retains the original provider response before this adaptation.
    """
    changed = False
    for choice in body.get("choices", []):
        message = choice.get("message", {})
        content = message.get("content")
        if not isinstance(content, list):
            continue
        texts, reasoning, opaque = [], [], []
        for block in content:
            if not isinstance(block, dict):
                raise ValueError("Invalid typed assistant content")
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                texts.append(block["text"])
            elif block.get("type") == "reasoning":
                opaque.append(block)
                for summary in block.get("summary") or []:
                    if summary.get("type") == "summary_text" and isinstance(
                        summary.get("text"), str
                    ):
                        reasoning.append(summary["text"])
                    elif summary.get("type") == "summary_encrypted_text" and isinstance(
                        summary.get("data"), str
                    ):
                        pass  # Preserve opaque encrypted contents; never decode them as answer text.
                    else:
                        raise ValueError("Unsupported reasoning summary")
            else:
                raise ValueError("Unsupported typed assistant content")
        message["content"] = "".join(texts) or None
        if reasoning:
            message["reasoning_content"] = "\n".join(reasoning)
        if opaque:
            message["databricks_reasoning"] = opaque
        changed = True
    return changed


def start(
    *,
    port=9001,
    workspace_fn=None,
    begin_call=None,
    finish_call=None,
    tool_strict_mode=None,
):
    tool_strict_mode = tool_strict_mode or os.environ.get(
        "DATABRICKS_TOOL_STRICT", "preserve"
    )
    if tool_strict_mode not in {"preserve", "omit"}:
        raise ValueError("DATABRICKS_TOOL_STRICT must be preserve or omit")
    retry_seconds = int(os.environ.get("DATABRICKS_RATE_LIMIT_RETRY_SECONDS", "60"))
    if not 0 <= retry_seconds <= 60:
        raise ValueError("DATABRICKS_RATE_LIMIT_RETRY_SECONDS must be between 0 and 60")
    workspace_fn = workspace_fn or lakebase.workspace
    begin_call = begin_call or lakebase.begin_call
    finish_call = finish_call or lakebase.finish_call
    endpoints = {
        "/v1/chat/completions": os.environ["EXTRACTION_MODEL_ENDPOINT"],
        "/v1/embeddings": os.environ["EMBEDDING_MODEL_ENDPOINT"],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            status, content, content_type = 502, b"", "application/json"
            retry_after = retry_after_ms = None
            call_id = None
            headers_sent = False
            response = None
            try:
                if self.path not in endpoints:
                    status = 404
                    raise ValueError("Unsupported API route")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8 * 1024 * 1024:
                    status = 413
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(size))
                model = payload.pop("model")
                if model != endpoints[self.path]:
                    status = 400
                    raise ValueError("Model is not bound to this API route")
                if self.path == "/v1/chat/completions" and tool_strict_mode == "omit":
                    for tool in payload.get("tools") or []:
                        if tool.get("type") == "function":
                            tool["function"].pop("strict", None)
                call_id = begin_call(model)
                workspace = workspace_fn()
                response = requests.post(
                    workspace.config.host.rstrip("/")
                    + "/serving-endpoints/"
                    + quote(model, safe="")
                    + "/invocations",
                    headers=workspace.config.authenticate(),
                    json=payload,
                    timeout=180,
                    stream=payload.get("stream") is True,
                )
                status = response.status_code
                retry_after = response.headers.get("Retry-After")
                retry_after_ms = response.headers.get("retry-after-ms")
                if (
                    status == 429
                    and not retry_after
                    and not retry_after_ms
                    and retry_seconds
                ):
                    retry_after = str(retry_seconds)
                content_type = response.headers.get("Content-Type", content_type)
                if response.ok and "text/event-stream" in content_type:
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    headers_sent = True
                    while chunk := response.raw.read1(65536, decode_content=True):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    # Streaming usage is explicitly unknown unless the caller
                    # independently records provider metadata.
                    finish_call(call_id, status, None)
                    call_id = None
                    return
                content = response.content
                usage = None
                if "application/json" in content_type and response.ok:
                    body = response.json()
                    usage = body.get("usage") if isinstance(body, dict) else None
                    if (
                        self.path == "/v1/chat/completions"
                        and isinstance(body, dict)
                        and normalize_chat_content(body)
                    ):
                        content = json.dumps(body).encode()
                finish_call(call_id, status, usage)
                call_id = None
            except Exception as exc:
                if status not in {400, 404, 413}:
                    status = 502
                if call_id is not None:
                    try:
                        finish_call(call_id, None, {"error_type": type(exc).__name__})
                    except Exception:
                        pass
                if headers_sent:
                    self.close_connection = True
                    return
                content = json.dumps(
                    {
                        "error": {
                            "type": "databricks_transport_error",
                            "message": type(exc).__name__,
                        }
                    }
                ).encode()
            finally:
                if response is not None:
                    response.close()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            for header, value in (
                ("Retry-After", retry_after),
                ("retry-after-ms", retry_after_ms),
            ):
                if value and len(value) <= 128 and not any(c in value for c in "\r\n"):
                    self.send_header(header, value)
            self.end_headers()
            self.wfile.write(content)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
