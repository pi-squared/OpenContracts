"""Drive the native composed extract/PDF screen with real browser pointer and input events."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

from prepared_source import verify_prepared

ROOT = Path(__file__).resolve().parents[1]

PDF_DECODER = """
export const GlobalWorkerOptions = {};
export const getDocument = () => ({promise: Promise.resolve({
  numPages: 3,
  getPage: async pageNumber => ({
    pageNumber,
    getViewport: ({scale}) => ({width: 600 * scale, height: 800 * scale,
      convertToViewportRectangle: ([x1, y1, x2, y2]) => [x1 * scale, (800-y1) * scale, x2 * scale, (800-y2) * scale]}),
    render: () => ({promise: Promise.resolve(), cancel: () => {}}),
    getAnnotations: async () => [{id: "fixture-link", subtype: "Link", url: "https://example.invalid/evidence", rect: [350, 590, 400, 610]}],
  }),
})});
"""
DOCUMENT_BYTES = """
export const getCachedPDFUrl = async url => url;
export const getPawlsLayer = async url => url.includes("-mouse") ? [0, 1].map(index => ({
  page: {index, width: 600, height: 800},
  tokens: [{x: 60, y: 200, width: 55, height: 20, text: "Shared"},
    {x: 130, y: 200, width: 65, height: 20, text: "passage."}],
})) : [];
export const getDocumentRawText = async () => "";
export const getDocxBytes = async () => new Uint8Array();
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--node-bin", type=Path, required=True)
    parser.add_argument("--chromium-executable", type=Path)
    parser.add_argument("--firefox-executable", type=Path)
    parser.add_argument("--campaign", choices=("focus", "mouse", "lifecycle", "input"), default="focus")
    args = parser.parse_args()
    verify_prepared(args.upstream.resolve(), ROOT)
    frontend = args.upstream.resolve() / "frontend"
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        port = handle.getsockname()[1]
    with tempfile.TemporaryDirectory(
        prefix="port-browser-", dir=frontend
    ) as temporary:
        destination = Path(temporary)
        campaign = f"extract-evidence-{args.campaign}.mjs"
        for name in ("extract-evidence-focus.tsx", campaign):
            shutil.copyfile(ROOT / "tests/browser" / name, destination / name)
        (destination / "index.html").write_text(
            '<div id="root"></div><script type="module" '
            f'src="/{destination.name}/extract-evidence-focus.tsx"></script>'
        )
        (destination / "pdf-decoder.ts").write_text(PDF_DECODER)
        (destination / "document-bytes.ts").write_text(DOCUMENT_BYTES)
        config = destination / "vite.config.mts"
        configuration = r"""
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
export default defineConfig({
  define: {"import.meta.env.VITE_EVIDENCE_CAMPAIGN": EVIDENCE_CAMPAIGN_VALUE},
  plugins: [react(), {
    name: "composed-route-reload",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (/^\/(d|e)\//.test(req.url ?? "")) {
          const query = (req.url ?? "").split("?")[1];
          req.url = FIXTURE_ROUTE + (query ? "?" + query : "");
        }
        next();
      });
    },
  }],
  resolve: {alias: [
    {find: /^pdfjs-dist$/, replacement: PDF_DECODER_PATH},
    {find: /^.*\/api\/cachedRest$/, replacement: DOCUMENT_BYTES_PATH},
  ]},
  server: {host: "127.0.0.1", strictPort: true},
});
"""
        for placeholder, value in (
            ("EVIDENCE_CAMPAIGN_VALUE", json.dumps(args.campaign)),
            ("FIXTURE_ROUTE", f"/{destination.name}/index.html"),
            ("PDF_DECODER_PATH", str(destination / "pdf-decoder.ts")),
            ("DOCUMENT_BYTES_PATH", str(destination / "document-bytes.ts")),
        ):
            configuration = configuration.replace(placeholder, json.dumps(value))
        config.write_text(configuration)
        node = str(args.node_bin.resolve() / "node")
        env = {
            **os.environ,
            "PATH": str(args.node_bin.resolve()) + os.pathsep + os.environ["PATH"],
            "EVIDENCE_TEST_URL": (
                f"http://127.0.0.1:{port}/{destination.name}/index.html"
                + ("?lifecycle=1&target=1" if args.campaign == "lifecycle" else "")
            ),
        }
        for key, path in (
            ("EVIDENCE_CHROMIUM", args.chromium_executable),
            ("EVIDENCE_FIREFOX", args.firefox_executable),
        ):
            if path:
                env[key] = str(path.resolve())
        with (destination / "vite.log").open("w+") as log:
            server = subprocess.Popen(
                [node, "node_modules/vite/bin/vite.js", "--config", str(config),
                 "--port", str(port)],
                cwd=frontend, env=env, stdout=log, stderr=log,
            )
            try:
                deadline = time.monotonic() + 30
                while True:
                    try:
                        urllib.request.urlopen(env["EVIDENCE_TEST_URL"], timeout=1).close()
                        break
                    except OSError:
                        if time.monotonic() > deadline or server.poll() is not None:
                            raise RuntimeError("Composed browser fixture did not start")
                        time.sleep(0.2)
                return subprocess.run(
                    [node, str(destination / campaign)],
                    cwd=frontend, env=env,
                ).returncode
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
