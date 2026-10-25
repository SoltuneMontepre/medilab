"""Run isolated CloudBeaver containers; never load a Kubernetes context or production credentials."""

import hashlib
import http.cookiejar
import json
import os
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "docker.io/dbeaver/cloudbeaver:26.2.2"
PASSWORD = "LocalRegression9"
SPECIAL_USER = 'regression"\\user'
SPECIAL_PASSWORD = "Regression9\"'\\\n\t$`unicode-ệ"


def engine(*args, check=True, input=None):
    result = subprocess.run(
        [os.environ.get("CONTAINER_ENGINE", "docker"), *args],
        input=input,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        # Container logs and command arguments can contain synthetic credentials.
        raise RuntimeError(f"Container operation {args[0]} failed (exit {result.returncode}).")
    return result


class Runtime:
    def __init__(self, guarded=True, admin="operator", volume=None):
        self.name = "medilab-cb-test-" + uuid.uuid4().hex[:12]
        self.volume = volume or self.name + "-workspace"
        self.owns_volume = volume is None
        self.bin_volume = self.name + "-classes"
        self.guarded = guarded
        self.network = None
        self.env = {
            "CB_SERVER_NAME": "Regression",
            "CB_ADMIN_NAME": admin,
            "CB_ADMIN_PASSWORD": PASSWORD,
            "DB_HOST": "127.0.0.1",
            "DB_USER": SPECIAL_USER,
            "DB_PASSWORD": SPECIAL_PASSWORD,
        }
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        if self.owns_volume:
            engine("volume", "create", self.volume)
        engine("volume", "create", self.bin_volume)
        self.port = None

    def mounts(self):
        return [
            "-v",
            f"{self.volume}:/opt/cloudbeaver/workspace",
            "-v",
            f"{self.bin_volume}:/bootstrap-bin",
            "-v",
            f"{ROOT / 'infra/cluster/cloudbeaver/bootstrap'}:/bootstrap:ro",
            "-v",
            f"{ROOT / 'tools/cloudbeaver'}:/regression:ro",
        ]

    def environment(self):
        return [value for key, value in self.env.items() for value in ("-e", key + "=" + value)]

    def helper(self, command, check=True):
        return engine(
            "run",
            "--rm",
            *self.mounts(),
            *self.environment(),
            "--entrypoint",
            "/bin/bash",
            IMAGE,
            "-c",
            command,
            check=check,
        )

    def prepare(self, check=True):
        return self.helper("/bin/bash /bootstrap/prepare.sh", check=check)

    def start(self):
        command = ["--entrypoint", "/bin/bash"] if self.guarded else []
        engine(
            "run",
            "-d",
            "--name",
            self.name,
            "-p",
            "127.0.0.1::8978",
            *(["--network", self.network] if self.network else []),
            *self.mounts(),
            *self.environment(),
            *command,
            IMAGE,
            *(["/bootstrap/start.sh"] if self.guarded else []),
        )
        binding = engine("port", self.name, "8978").stdout.strip()
        if binding:
            self.port = int(binding.rsplit(":", 1)[1])

    def query(self, query, variables=None, errors=False):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/gql",
            data=json.dumps({"query": query, "variables": variables or {}}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with self.opener.open(request, timeout=8) as response:
            result = json.load(response)
        if result.get("errors") and not errors:
            messages = "; ".join(error.get("message", "GraphQL failure") for error in result["errors"])
            for key in ("CB_ADMIN_PASSWORD", "DB_PASSWORD"):
                messages = messages.replace(self.env[key], "[REDACTED]")
            raise AssertionError(messages)
        return result

    def wait(self, configuration_mode=False):
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            try:
                data = self.query("{ serverConfig { configurationMode } }")
                if data["data"]["serverConfig"]["configurationMode"] is configuration_mode:
                    return
            except (OSError, ValueError, KeyError, AssertionError):
                pass
            time.sleep(1)
        raise AssertionError("CloudBeaver did not reach expected configuration state within 100s.")

    def login(self):
        self.query("mutation { openSession { valid } }")
        self.query(
            'query($credentials: Object!) { authLogin(provider: "local", credentials: $credentials) { authStatus } }',
            {"credentials": {"user": "operator", "password": hashlib.md5(PASSWORD.encode()).hexdigest().upper()}},
        )
        return self.query("{ activeUser { userId } }")["data"]["activeUser"]["userId"]

    def ready(self):
        return engine("exec", self.name, "/bin/bash", "/bootstrap/ready.sh", check=False).returncode == 0

    def stop(self):
        engine("stop", "--time", "30", self.name, check=False)
        engine("rm", self.name, check=False)

    def read(self, relative):
        return self.helper("cat /opt/cloudbeaver/workspace/" + relative).stdout

    def write(self, relative, content):
        engine(
            "run",
            "--rm",
            "-i",
            *self.mounts(),
            "--entrypoint",
            "/bin/bash",
            IMAGE,
            "-c",
            'umask 077; mkdir -p "$(dirname "$1")"; cat > "$1"',
            "test",
            "/opt/cloudbeaver/workspace/" + relative,
            input=content,
        )

    def close(self):
        self.stop()
        engine("volume", "rm", self.bin_volume, check=False)
        if self.owns_volume:
            engine("volume", "rm", self.volume, check=False)
