"""Exercise native multipart fetches through the Apps/JWT header boundary."""

import json
import shutil
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "port/python"))
from databricks_port.token_transport import (  # noqa: E402
    TOKEN_TRANSPORT_SCRIPT,
    BackendTokenHeaderMiddleware,
)


class BrowserTokenTransportTests(unittest.TestCase):
    def test_native_upload_body_and_two_authentication_headers(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the browser transport check")

        class Receiver(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = SimpleNamespace(
                    path=self.path,
                    META={
                        "HTTP_AUTHORIZATION": self.headers.get("Authorization"),
                        "HTTP_X_OPENCONTRACTS_AUTHORIZATION": self.headers.get(
                            "X-OpenContracts-Authorization"
                        ),
                    },
                )
                authorization = BackendTokenHeaderMiddleware(
                    lambda req: req.META["HTTP_AUTHORIZATION"]
                )(request)
                response = json.dumps(
                    {
                        "authorization": authorization,
                        "proxy_authorization": self.headers.get("Authorization"),
                        "backend_header": request.META[
                            "HTTP_X_OPENCONTRACTS_AUTHORIZATION"
                        ],
                        "content_type": self.headers.get("Content-Type"),
                        "body": self.rfile.read(
                            int(self.headers["Content-Length"])
                        ).decode(),
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        servers = [ThreadingHTTPServer(("127.0.0.1", 0), Receiver) for _ in range(2)]
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        origin, other = (f"http://127.0.0.1:{s.server_port}" for s in servers)
        script = (
            "const origin=" + json.dumps(origin) + ",other=" + json.dumps(other) + ";"
            "const nativeFetch=globalThis.fetch;"
            "globalThis.window={location:{origin},fetch:(input,init={})=>{"
            "const headers=new Headers(init.headers||(input instanceof Request?input.headers:undefined));"
            "if(!headers.has('Authorization'))headers.set('Authorization','Bearer fixture-workspace-oauth');"
            "return nativeFetch(input,{...init,headers});}};"
            + TOKEN_TRANSPORT_SCRIPT
            + """
            const results=[];
            for(const [base,path,asRequest,withToken] of [
              [origin,'/graphql/',false,true],
              [origin,'/api/imports/documents/',false,true],
              [origin,'/api/imports/chunked/fixture/complete/',true,true],
              [origin,'/api/imports-extra/',false,true],
              [origin,'/api/health',false,true],
              [other,'/api/imports/documents/',false,true],
              [origin,'/api/imports/documents/',false,false],
            ]){
              const body=new FormData();body.append('title','Public fixture');
              body.append('file',new Blob(['public-pdf-bytes']), 'fixture.pdf');
              const init={method:'POST',body,headers:withToken?{Authorization:'Bearer fixture-native-jwt'}:{}};
              const input=asRequest?new Request(base+path,init):base+path;
              const response=await window.fetch(input,asRequest?undefined:init);
              results.push(await response.json());
            }
            process.stdout.write(JSON.stringify(results));
            """
        )
        try:
            result = subprocess.run(
                [node, "--input-type=module", "-e", script],
                check=True,
                text=True,
                capture_output=True,
                timeout=20,
            )
            rows = json.loads(result.stdout)
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
        for row in rows[:3]:
            self.assertEqual(
                row["proxy_authorization"], "Bearer fixture-workspace-oauth"
            )
            self.assertEqual(row["backend_header"], "Bearer fixture-native-jwt")
            self.assertEqual(row["authorization"], "Bearer fixture-native-jwt")
        for row in rows[3:6]:
            self.assertEqual(row["proxy_authorization"], "Bearer fixture-native-jwt")
            self.assertIsNone(row["backend_header"])
        self.assertEqual(rows[6]["authorization"], "Bearer fixture-workspace-oauth")
        self.assertIsNone(rows[6]["backend_header"])
        for row in rows:
            self.assertIn("multipart/form-data; boundary=", row["content_type"])
            self.assertIn('name="title"', row["body"])
            self.assertIn("Public fixture", row["body"])
            self.assertIn('filename="fixture.pdf"', row["body"])
            self.assertIn("public-pdf-bytes", row["body"])

    def test_backend_header_does_not_replace_oauth_on_unrelated_routes(self):
        for path in ("/api/health", "/api/imports", "/api/imports-extra/", "/graphql"):
            request = SimpleNamespace(
                path=path,
                META={
                    "HTTP_AUTHORIZATION": "Bearer fixture-workspace-oauth",
                    "HTTP_X_OPENCONTRACTS_AUTHORIZATION": "Bearer fixture-native-jwt",
                },
            )
            actual = BackendTokenHeaderMiddleware(
                lambda req: req.META["HTTP_AUTHORIZATION"]
            )(request)
            self.assertEqual(actual, "Bearer fixture-workspace-oauth")


if __name__ == "__main__":
    unittest.main()
