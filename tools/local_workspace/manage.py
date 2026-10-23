"""Start/stop the isolated local application without deleting persistent data."""

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(command, *, env=None):
    return subprocess.run(
        command, check=True, env=env, cwd=ROOT, text=True, capture_output=True
    ).stdout


def configuration(state):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state / "config.json"
    if not path.exists():
        data = {
            "database_password": secrets.token_urlsafe(32),
            "secret_key": secrets.token_urlsafe(48),
            "owner_password": secrets.token_urlsafe(32),
            "owner": "owner",
            "prefix": "/opencontracts",
            "public_origin": "http://127.0.0.1:4400",
            "port": 4400,
            "database_port": 55461,
            "redis_port": 55462,
            "container_prefix": "oc-local-hp-20261021",
        }
        path.write_text(json.dumps(data, indent=2))
        path.chmod(0o600)
    return json.loads(path.read_text())


def environment(state, config):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("AZURE_", "DATABRICKS_", "GH_", "GITHUB_"))
    }
    env.update(
        DJANGO_SETTINGS_MODULE="config.settings.workspace",
        DJANGO_READ_DOT_ENV_FILE="false",
        DATABASE_URL=(
            f"postgresql://opencontracts:{config['database_password']}"
            f"@127.0.0.1:{config['database_port']}/opencontracts"
        ),
        REDIS_URL=f"redis://127.0.0.1:{config['redis_port']}/0",
        DJANGO_SECRET_KEY=config["secret_key"],
        LOCAL_WORKSPACE_STATE=str(state),
        LOCAL_OWNER_USERNAME=config["owner"],
        LOCAL_OWNER_PASSWORD=config["owner_password"],
        APP_BASE_PATH=config["prefix"],
        APP_PUBLIC_ORIGIN=config["public_origin"],
        WORKFLOW_PACKAGE_ROOT=str(state / "workflows"),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=str(ROOT),
        DEFAULT_LLM="openai:gpt-6-luna",
        OPENAI_EMBEDDING_MODEL="text-embedding-3-small",
        OPENAI_EMBEDDING_DIMENSIONS="1536",
        WARP_INGEST_PARSER_SERVICE_URL=f"http://127.0.0.1:{config.get('warp_port', 4403)}/api/parse",
    )
    env["WARP_INGEST_API_KEY"] = (
        (state / "warp.env").read_text().strip().partition("=")[2]
    )
    return env


def owned_container(state, name):
    """Inspect lifecycle metadata only; refuse a foreign same-name container."""
    found = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{json .State.Running}} {{json .Config.Labels}}",
            name,
        ],
        capture_output=True,
        text=True,
    )
    if found.returncode:
        if "No such" in found.stderr:
            return None
        raise RuntimeError("Cannot inspect the owned local container")
    running, labels = found.stdout.strip().split(" ", 1)
    if json.loads(labels).get("opencontracts.workspace") != str(state):
        raise RuntimeError("Refusing to operate a foreign same-name container")
    return json.loads(running)


def active(pidfile, marker):
    try:
        pid = int(pidfile.read_text())
        return (
            marker.encode() in Path(f"/proc/{pid}/cmdline").read_bytes()
            and Path(f"/proc/{pid}/cwd").resolve() == ROOT
        )
    except (FileNotFoundError, ValueError, ProcessLookupError):
        return False


def start_process(state, name, command, env):
    pidfile = state / f"{name}.pid"
    if active(pidfile, command[2]):
        return
    with (state / f"{name}.log").open("ab") as log:
        process = subprocess.Popen(
            command,
            env=env,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    pidfile.write_text(str(process.pid))


def stop_processes(state):
    for name, marker in [("app", "uvicorn"), ("worker", "celery")]:
        pidfile = state / f"{name}.pid"
        if active(pidfile, marker):
            os.killpg(int(pidfile.read_text()), signal.SIGTERM)
            for _ in range(100):
                if not active(pidfile, marker):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError(f"Owned {name} did not stop cleanly")


def start(state, config, python):
    warp_env = state / "warp.env"
    if not warp_env.exists():
        warp_env.write_text("WARP_API_KEY=" + secrets.token_urlsafe(32) + "\n")
        warp_env.chmod(0o600)
    postgres_env = state / "postgres.env"
    postgres_env.write_text(
        "POSTGRES_USER=opencontracts\nPOSTGRES_DB=opencontracts\nPOSTGRES_PASSWORD="
        + config["database_password"]
        + "\n"
    )
    postgres_env.chmod(0o600)
    prefix = config["container_prefix"]
    containers = [
        (
            "warp",
            [
                "--env-file",
                str(warp_env),
                "-p",
                f"127.0.0.1:{config.get('warp_port', 4403)}:5001",
                "--cpus",
                "2",
                "--memory",
                "3g",
                "ghcr.io/open-source-legal/warp-ingest:1.0.0",
            ],
        ),
        (
            "postgres",
            [
                "--env-file",
                str(postgres_env),
                "-p",
                f"127.0.0.1:{config['database_port']}:5432",
                "-v",
                prefix + "-postgres:/var/lib/postgresql/data",
                "pgvector/pgvector:pg17",
                "-c",
                "shared_buffers=128MB",
                "-c",
                "max_connections=50",
            ],
        ),
        (
            "redis",
            [
                "-p",
                f"127.0.0.1:{config['redis_port']}:6379",
                "-v",
                prefix + "-redis:/data",
                "redis:7-alpine",
                "redis-server",
                "--appendonly",
                "yes",
            ],
        ),
    ]
    for name, args in containers:
        container = prefix + "-" + name
        running = owned_container(state, container)
        if running is None:
            run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container,
                    "--label",
                    "opencontracts.workspace=" + str(state),
                    *args,
                ]
            )
        elif not running:
            run(["docker", "start", container])
    for _ in range(60):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{config.get('warp_port', 4403)}/healthz", timeout=2
            ) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(1)
    else:
        raise RuntimeError("Local Warp OCR service did not become ready")
    for _ in range(60):
        result = subprocess.run(
            [
                "docker",
                "exec",
                prefix + "-postgres",
                "pg_isready",
                "-U",
                "opencontracts",
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Local PostgreSQL did not become ready")
    env = environment(state, config)
    run([python, "manage.py", "migrate", "--noinput"], env=env)
    run(
        [
            python,
            "manage.py",
            "migrate_pipeline_settings",
            "--component",
            "OpenAIEmbedder",
            "--strict",
        ],
        env=env,
    )
    run(
        [
            python,
            "manage.py",
            "migrate_pipeline_settings",
            "--component",
            "WarpIngestParser",
            "--strict",
        ],
        env=env,
    )
    run(
        [
            python,
            "manage.py",
            "migrate_pipeline_settings",
            "--sync-preferences",
            "--init-only",
        ],
        env=env,
    )
    run([python, "-m", "tools.local_workspace.bootstrap"], env=env)
    start_process(
        state,
        "worker",
        [
            python,
            "-m",
            "celery",
            "-A",
            "config.celery_app",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--loglevel=WARNING",
            "--without-gossip",
            "--without-mingle",
        ],
        env,
    )
    start_process(
        state,
        "app",
        [
            python,
            "-m",
            "uvicorn",
            "tools.local_workspace.asgi:application",
            "--host",
            "127.0.0.1",
            "--port",
            str(config["port"]),
            "--lifespan",
            "off",
            "--no-access-log",
        ],
        env,
    )
    url = f"http://127.0.0.1:{config['port']}{config['prefix']}/__api/api/health/"
    for _ in range(60):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError(
        "Local application did not become ready; inspect the private app.log"
    )


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "restart", "stop", "status", "env"])
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    state = args.state.resolve()
    config = configuration(state)
    if args.action in {"start", "restart"}:
        if args.action == "restart":
            stop_processes(state)
        start(state, config, args.python)
    elif args.action == "stop":
        stop_processes(state)
        for name in ["postgres", "redis", "warp"]:
            container = config["container_prefix"] + "-" + name
            if owned_container(state, container):
                run(["docker", "stop", container])
    elif args.action == "env":
        raise SystemExit(
            "Environment contains credentials and is never printed. Import environment() programmatically."
        )
    print(
        json.dumps(
            {
                "app_running": active(state / "app.pid", "uvicorn"),
                "worker_running": active(state / "worker.pid", "celery"),
                "local_url": f"http://127.0.0.1:{config['port']}{config['prefix']}/",
                "browser_url": config["public_origin"] + config["prefix"] + "/",
                "state_directory": str(state),
            }
        )
    )


if __name__ == "__main__":
    main()
