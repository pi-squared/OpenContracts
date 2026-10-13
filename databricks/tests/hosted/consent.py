"""Verify the port's first visit in an actual hosted app with empty storage."""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from databricks.sdk import WorkspaceClient
from graphql import OperationDefinitionNode, OperationType, parse
from playwright.sync_api import sync_playwright


def run(profile, app_name, destination, scenario="consent"):
    """Capture authentic browser evidence; do not submit consent or app edits."""
    os.umask(0o077)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    client = WorkspaceClient(profile=profile)
    app = client.apps.get(app_name)
    origin = app.url.rstrip("/")
    blocked = []

    def route_request(route):
        request = route.request
        parts = urlsplit(request.url)
        same_origin = f"{parts.scheme}://{parts.netloc}" == origin
        allowed = request.method in {"GET", "HEAD", "OPTIONS"}
        if (
            same_origin
            and parts.path.rstrip("/") == "/graphql"
            and request.method == "POST"
        ):
            try:
                payload = request.post_data_json
                operations = [
                    node
                    for node in parse(payload["query"]).definitions
                    if isinstance(node, OperationDefinitionNode)
                ]
                name = payload.get("operationName")
                selected = [
                    node
                    for node in operations
                    if not name or (node.name and node.name.value == name)
                ]
                allowed = (
                    len(selected) == 1 and selected[0].operation == OperationType.QUERY
                )
            except Exception:
                allowed = False
        if not allowed:
            blocked.append({"method": request.method, "path": parts.path})
            route.abort("blockedbyclient")
            return
        headers = dict(request.headers)
        if same_origin:
            headers.update(client.config.authenticate())
        try:
            response = route.fetch(headers=headers, max_redirects=0, timeout=30000)
            if response.status in {300, 301, 302, 303, 307, 308}:
                route.abort("blockedbyclient")
            else:
                route.fulfill(response=response)
        except Exception:
            route.abort("failed")

    checks = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900}, service_workers="block"
        )
        context.route("**/*", route_request)
        page = context.new_page()
        try:
            page.goto(
                origin + ("/extracts" if scenario == "keyboard" else "/documents"),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            if scenario == "keyboard":
                page.evaluate("localStorage.setItem('oc_cookieAccepted','true')")
                page.reload(wait_until="domcontentloaded")
                launcher = page.get_by_role("button", name="New Extract", exact=True)
                launcher.wait_for(timeout=30000)
                launcher.click()
                page.get_by_placeholder(
                    "Enter a descriptive name for your extract"
                ).wait_for()
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                checks["escape_dismisses"] = not page.get_by_placeholder(
                    "Enter a descriptive name for your extract"
                ).is_visible()
                checks["focus_returns"] = launcher.evaluate(
                    "e=>e===document.activeElement"
                )
            else:
                page.get_by_role("button", name="Upload", exact=True).wait_for(
                    timeout=30000
                )
                # Allow the mount effect to run before checking absence.
                page.wait_for_timeout(1000)
                checks["no_consent_popup"] = not page.get_by_role(
                    "button", name="Accept and continue", exact=True
                ).is_visible()
                checks["no_fabricated_local_acceptance"] = (
                    page.evaluate("localStorage.getItem('oc_cookieAccepted')") is None
                )
                checks["authenticated_owner"] = page.get_by_role(
                    "button", name="p pilot-owner", exact=True
                ).is_visible()
            if scenario == "consent":
                for path in ("/corpuses", "/extracts", "/documents"):
                    page.goto(origin + path, wait_until="domcontentloaded")
                    page.get_by_role(
                        "button", name="p pilot-owner", exact=True
                    ).wait_for(timeout=30000)
                    page.wait_for_timeout(500)
                    checks["no_popup_on_navigation_" + path[1:]] = not page.get_by_role(
                        "button", name="Accept and continue", exact=True
                    ).is_visible()
                checks["no_acceptance_after_navigation"] = (
                    page.evaluate("localStorage.getItem('oc_cookieAccepted')") is None
                )
            image = destination / "documents.png"
            page.screenshot(path=str(image))
            evidence = {
                "issue": "https://github.com/pi-squared/OpenContracts-Databricks/issues/"
                + str(100 if scenario == "keyboard" else 98),
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "viewport": page.viewport_size,
                "route": "/extracts" if scenario == "keyboard" else "/documents",
                "deployment": app.active_deployment.as_dict(),
                "checks": checks,
                "blocked_requests": blocked,
                "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "browser": browser.version,
            }
            (destination / "result.json").write_text(
                json.dumps(evidence, indent=2) + "\n"
            )
        finally:
            context.close()
            browser.close()
    print(json.dumps({"checks": checks, "passed": all(checks.values())}))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument(
        "--destination",
        type=Path,
        required=True,
        help="Fresh private evidence directory",
    )
    parser.add_argument(
        "--scenario", choices=["consent", "keyboard"], default="consent"
    )
    args = parser.parse_args()
    raise SystemExit(run(args.profile, args.app, args.destination, args.scenario))
