"""HTTP contract tests at the stock OpenAI API / Databricks serving boundary."""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import patch  # noqa: E402

import requests  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "port/python"))
from databricks_port.transport import start  # noqa: E402


class TransportFixture:
    def setUp(self):
        self.received, self.audit, self.auth_calls = [], [], []
        self.response = (
            b'{"choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":12}}'
        )
        self.status, self.retry_after = 200, None
        self.retry_after_ms = None
        self.streaming = False
        self.stream_continue = threading.Event()
        test = self

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                test.received.append(
                    (
                        self.path,
                        self.headers.get("Authorization"),
                        json.loads(
                            self.rfile.read(int(self.headers["Content-Length"]))
                        ),
                    )
                )
                self.send_response(test.status)
                self.send_header(
                    "Content-Type",
                    "text/event-stream" if test.streaming else "application/json",
                )
                if test.retry_after:
                    self.send_header("Retry-After", test.retry_after)
                if test.retry_after_ms:
                    self.send_header("retry-after-ms", test.retry_after_ms)
                self.end_headers()
                if test.streaming:
                    self.wfile.write(b'data: {"delta":"first"}\n\n')
                    self.wfile.flush()
                    if not test.stream_continue.wait(5):
                        return
                    self.wfile.write(b"data: [DONE]\n\n")
                    return
                self.wfile.write(test.response)

        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        threading.Thread(target=self.upstream.serve_forever, daemon=True).start()
        self.env = patch.dict(
            os.environ,
            {
                "EXTRACTION_MODEL_ENDPOINT": "fixture-sonnet",
                "EMBEDDING_MODEL_ENDPOINT": "fixture-embedding",
                "DATABRICKS_TOOL_STRICT": "preserve",
                "DATABRICKS_RATE_LIMIT_RETRY_SECONDS": "60",
            },
        )
        self.env.start()

        def authenticate():
            self.auth_calls.append(True)
            return {"Authorization": "Bearer test-app-oauth"}

        workspace = SimpleNamespace(
            config=SimpleNamespace(
                host=f"http://127.0.0.1:{self.upstream.server_port}",
                authenticate=authenticate,
            )
        )
        self.proxy = start(
            port=0,
            tool_strict_mode=getattr(self, "tool_strict_mode", None),
            workspace_fn=lambda: workspace,
            begin_call=lambda endpoint: len(self.audit) + 1,
            finish_call=lambda call_id, status, usage: self.audit.append(
                (call_id, status, usage)
            ),
        )
        self.base = f"http://127.0.0.1:{self.proxy.server_port}"

    def tearDown(self):
        self.stream_continue.set()
        self.proxy.shutdown()
        self.proxy.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()
        self.env.stop()


class TransportTests(TransportFixture, unittest.TestCase):
    def test_typed_reasoning_response_preserves_native_final_result_tool(self):
        body = {
            "id": "chat-fixture",
            "object": "chat.completion",
            "created": 1,
            "model": "gpt-oss-120b",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "reasoning",
                                "summary": [
                                    {
                                        "type": "summary_text",
                                        "text": "Synthetic reasoning summary",
                                    },
                                    {
                                        "type": "summary_encrypted_text",
                                        "data": "opaque-fixture",
                                    },
                                ],
                            }
                        ],
                        "tool_calls": [
                            {
                                "id": "call-fixture",
                                "type": "function",
                                "function": {
                                    "name": "final_result",
                                    "arguments": '{"state":"supported"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
        }
        self.response = json.dumps(body).encode()
        response = requests.post(
            self.base + "/v1/chat/completions",
            json={"model": "fixture-sonnet", "messages": []},
            timeout=5,
        )
        self.assertEqual(response.status_code, 200)
        from openai import AsyncOpenAI
        from openai.types.chat import ChatCompletion
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        client = AsyncOpenAI(api_key="synthetic", base_url=self.base + "/v1")
        model = OpenAIChatModel(
            "gpt-oss-120b", provider=OpenAIProvider(openai_client=client)
        )
        parsed = model._process_response(ChatCompletion.model_validate(response.json()))
        calls = [part for part in parsed.parts if part.part_kind == "tool-call"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].tool_name, "final_result")
        self.assertEqual(calls[0].args, '{"state":"supported"}')
        self.assertEqual(response.json()["choices"][0]["message"]["content"], None)
        self.assertEqual(
            response.json()["choices"][0]["message"]["reasoning_content"],
            "Synthetic reasoning summary",
        )
        self.assertEqual(
            response.json()["choices"][0]["message"]["databricks_reasoning"],
            body["choices"][0]["message"]["content"],
        )
        self.assertEqual(self.audit, [(1, 200, body["usage"])])

    def test_stock_structured_request_and_response_are_preserved(self):
        payload = {
            "model": "fixture-sonnet",
            "messages": [{"role": "user", "content": "A bounded fixture"}],
            "temperature": 0,
            "max_completion_tokens": 256,
            "tool_choice": "required",
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "emit",
                        "strict": True,
                        "parameters": {"type": "object"},
                    },
                }
            ],
        }
        response = requests.post(
            self.base + "/v1/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer browser-token"},
            timeout=5,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.response)
        self.assertEqual(
            self.received,
            [
                (
                    "/serving-endpoints/fixture-sonnet/invocations",
                    "Bearer test-app-oauth",
                    {key: value for key, value in payload.items() if key != "model"},
                )
            ],
        )
        self.assertEqual(self.audit, [(1, 200, {"prompt_tokens": 12})])

    def test_embedding_inputs_and_provider_errors_are_preserved(self):
        self.status, self.retry_after = 429, "17"
        self.response = (
            b'{"error_code":"REQUEST_LIMIT_EXCEEDED","message":"retry later"}'
        )
        response = requests.post(
            self.base + "/v1/embeddings",
            json={"model": "fixture-embedding", "input": ["one", "two"]},
            timeout=5,
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.content, self.response)
        self.assertEqual(response.headers["Retry-After"], "17")
        self.assertEqual(self.received[0][2], {"input": ["one", "two"]})
        self.assertEqual(self.audit, [(1, 429, None)])

    def test_models_must_match_the_bound_route(self):
        response = requests.post(
            self.base + "/v1/embeddings",
            json={"model": "fixture-sonnet", "input": "one"},
            timeout=5,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.received, [])
        self.assertEqual(self.audit, [])

    def test_rate_limit_without_provider_hint_uses_bounded_retry_header(self):
        self.status = 429
        response = requests.post(
            self.base + "/v1/chat/completions",
            json={"model": "fixture-sonnet", "messages": []},
            timeout=5,
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.content, self.response)
        self.assertEqual(response.headers["Retry-After"], "60")

    def test_invalid_strict_mode_fails_before_listening(self):
        with self.assertRaises(ValueError):
            start(port=0, tool_strict_mode="automatic")
        with patch.dict(os.environ, {"DATABRICKS_RATE_LIMIT_RETRY_SECONDS": "61"}):
            with self.assertRaises(ValueError):
                start(port=0)

    def test_provider_millisecond_retry_hint_is_preserved(self):
        self.status, self.retry_after_ms = 429, "1000"
        response = requests.post(
            self.base + "/v1/chat/completions",
            json={"model": "fixture-sonnet", "messages": []},
            timeout=5,
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.content, self.response)
        self.assertEqual(response.headers["retry-after-ms"], "1000")
        self.assertNotIn("Retry-After", response.headers)

    def test_each_call_uses_the_sdk_renewable_authenticator(self):
        for _ in range(2):
            response = requests.post(
                self.base + "/v1/embeddings",
                json={"model": "fixture-embedding", "input": "one"},
                timeout=5,
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.auth_calls), 2)

    def test_stream_reaches_client_before_provider_finishes(self):
        self.streaming = True
        with requests.post(
            self.base + "/v1/chat/completions",
            json={"model": "fixture-sonnet", "messages": [], "stream": True},
            stream=True,
            timeout=2,
        ) as response:
            lines = response.iter_lines(chunk_size=1)
            self.assertEqual(next(lines), b'data: {"delta":"first"}')
            self.assertFalse(self.stream_continue.is_set())
            self.stream_continue.set()
            self.assertIn(b"data: [DONE]", list(lines))


class NonStrictTransportTests(TransportFixture, unittest.TestCase):
    tool_strict_mode = "omit"

    def test_omit_only_changes_function_transport_flag(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"strict": {"type": "string"}},
            "required": ["strict"],
        }
        response = requests.post(
            self.base + "/v1/chat/completions",
            json={
                "model": "fixture-sonnet",
                "messages": [{"role": "user", "content": "Bounded fixture"}],
                "tool_choice": "required",
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "emit",
                            "strict": True,
                            "parameters": schema,
                        },
                    }
                ],
            },
            timeout=5,
        )
        self.assertEqual(response.status_code, 200)
        forwarded = self.received[0][2]
        self.assertNotIn("strict", forwarded["tools"][0]["function"])
        self.assertEqual(forwarded["tools"][0]["function"]["parameters"], schema)
        self.assertEqual(forwarded["tool_choice"], "required")
        self.assertEqual(
            forwarded["messages"], [{"role": "user", "content": "Bounded fixture"}]
        )


if __name__ == "__main__":
    unittest.main()
