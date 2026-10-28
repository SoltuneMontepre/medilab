"""Inspect selected worker/config fields without exposing environment secrets or full configuration."""

import json

from .run import DOCKER, DOCKER_ENV, PROJECT, command, require_success, write_result

SCRIPT = r"""
import json, pathlib
root = pathlib.Path('/etc/onlyoffice/documentserver')
def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = v
config = {}
loaded = []
for filename in ('default.json', 'production.json', 'production-linux.json',
                 'local.json', 'local-production.json', 'local-production-linux.json'):
    path = root / filename
    if path.exists():
        merge(config, json.loads(path.read_text()))
        loaded.append(filename)
workers = []
for path in pathlib.Path('/proc').glob('[0-9]*'):
    try:
        name = (path / 'comm').read_text().strip()
        if name in ('docservice', 'converter'):
            env = dict(item.split(b'=', 1) for item in (path / 'environ').read_bytes().split(b'\0') if b'=' in item)
            worker = {'pid': int(path.name), 'name': name, 'NODE_CONFIG_present': b'NODE_CONFIG' in env}
            if b'NODE_CONFIG' in env:
                override = json.loads(env[b'NODE_CONFIG'])['services']['CoAuthoring']
                worker['override_callback_timeout'] = override.get('server', {}).get('callbackRequestTimeout')
                worker['override_cache_seconds'] = override.get('expire', {}).get('files')
            workers.append(worker)
    except (FileNotFoundError, PermissionError):
        pass
c = config['services']['CoAuthoring']
print(json.dumps({'workers': workers, 'loaded_files': loaded, 'disk_settings': {
    'callbackRequestTimeout': c['server']['callbackRequestTimeout'],
    'expire.files': c['expire']['files'],
    'outbox.inBody': c['token']['outbox']['inBody'],
    'outbox.expires': c['token']['outbox']['expires'],
    'callbackBackoffOptions': c['callbackBackoffOptions']}}))
"""


def probe():
    identifiers = require_success(
        command(
            [
                *DOCKER,
                "ps",
                "-q",
                "--filter",
                "label=com.docker.compose.project=" + PROJECT,
                "--filter",
                "label=com.docker.compose.service=documentserver",
                "--filter",
                "status=running",
            ],
            env=DOCKER_ENV,
        ),
        "Find isolated server",
    ).stdout.split()
    if len(identifiers) != 1:
        raise RuntimeError("Expected exactly one running server in this isolated project.")
    inspector = "/opt/medilab/onlyoffice/inspect_config.py"
    mounted = command([*DOCKER, "exec", identifiers[0], "test", "-f", inspector], env=DOCKER_ENV)
    if mounted.returncode == 0:
        output = require_success(
            command([*DOCKER, "exec", "--user", "ds", identifiers[0], "python3", inspector], env=DOCKER_ENV),
            "Verify native effective worker policy",
        )
        write_result(
            "effective-runtime.json",
            {
                "source": "config.get inside each native worker after its original entrypoint",
                "workers": [json.loads(line) for line in output.stdout.splitlines()],
                "status": "PASS",
            },
        )
        return
    output = require_success(
        command([*DOCKER, "exec", "-i", "--user", "ds", identifiers[0], "python3", "-"], input=SCRIPT, env=DOCKER_ENV),
        "Inspect worker settings",
    )
    result = json.loads(output.stdout)
    result["note"] = "Whitelisted disk fields and worker overrides; not a full Node config resolver or TLS/drain proof."
    write_result("effective-runtime.json", result)


if __name__ == "__main__":
    probe()
