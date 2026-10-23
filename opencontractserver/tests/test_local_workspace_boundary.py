"""The loopback bridge must not accept a browser's claimed application identity."""

from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase, override_settings


@override_settings(
    APP_BASE_PATH="/opencontracts", APP_PUBLIC_ORIGIN="https://bridge.example"
)
class LocalWorkspaceBoundaryTests(SimpleTestCase):
    async def request(self, headers):
        from tools.local_workspace import asgi

        responses = []
        backend = AsyncMock()

        async def send(value):
            responses.append(value)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/opencontracts/__api/graphql/",
            "headers": headers,
            "query_string": b"",
        }
        with patch.object(asgi, "backend", backend), patch.object(
            asgi, "owner_token", AsyncMock(return_value="native-owner-token")
        ) as token:
            await asgi.application(scope, AsyncMock(), send)
        return backend, token, responses

    async def test_public_host_and_stripped_browser_authorization_use_native_owner(
        self,
    ):
        backend, token, _ = await self.request(
            [(b"host", b"bridge.example"), (b"origin", b"https://bridge.example")]
        )
        headers = dict(backend.call_args.args[0]["headers"])
        self.assertEqual(headers[b"host"], b"bridge.example")
        self.assertEqual(headers[b"authorization"], b"Bearer native-owner-token")
        token.assert_awaited_once()

    async def test_client_bearer_and_cookie_never_choose_the_owner_identity(self):
        backend, _, _ = await self.request(
            [
                (b"authorization", b"Bearer untrusted-client-token"),
                (b"cookie", b"session=untrusted"),
                (b"origin", b"http://127.0.0.1:4400"),
            ]
        )
        headers = dict(backend.call_args.args[0]["headers"])
        self.assertNotIn(b"cookie", headers)
        self.assertEqual(headers[b"authorization"], b"Bearer native-owner-token")

    async def test_null_and_unexpected_origins_are_rejected_before_token_issuance(self):
        for origin in [
            b"null",
            b"https://attacker.example",
            b"https://bridge.example.attacker.example",
        ]:
            backend, token, responses = await self.request([(b"origin", origin)])
            backend.assert_not_awaited()
            token.assert_not_awaited()
            self.assertEqual(responses[0]["status"], 403)

    async def test_no_origin_is_permitted_for_trusted_local_tools(self):
        backend, _, _ = await self.request([])
        backend.assert_awaited_once()
