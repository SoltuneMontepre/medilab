"""Check actual worker environments and report only approved non-secret policy fields."""

import json
import sys
from pathlib import Path


def main():
    expected = json.loads(Path("/opt/medilab/onlyoffice/settings.json").read_text(encoding="utf-8"))
    found = set()
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            name = (process / "comm").read_text(encoding="utf-8").strip()
            if name not in {"docservice", "converter"}:
                continue
            env = dict(
                value.split(b"=", 1) for value in (process / "environ").read_bytes().split(b"\0") if b"=" in value
            )
            if (
                env.get(b"NODE_ENV") != b"production-linux"
                or env.get(b"NODE_CONFIG_DIR") != b"/etc/onlyoffice/documentserver"
            ):
                raise RuntimeError("Unexpected worker configuration context")
            actual = json.loads(env[b"NODE_CONFIG"])
            if actual != expected:
                raise RuntimeError("Worker configuration differs from the committed settings")
            config = actual["services"]["CoAuthoring"]
            outbox = config["token"]["outbox"]
            report = {
                "worker": name,
                "pid": int(process.name),
                "callbackRequestTimeout": config["server"]["callbackRequestTimeout"],
                "cache_files": config["expire"]["files"],
                "outbox": {
                    key: outbox[key]
                    for key in ["header", "prefix", "inBody", "algorithm", "expires", "urlExclusionRegex"]
                },
                "tlsVerification": config["requestDefaults"]["rejectUnauthorized"],
            }
            sys.stdout.write(json.dumps(report) + "\n")
            found.add(name)
        except (FileNotFoundError, ProcessLookupError):
            continue
    if found != {"docservice", "converter"}:
        raise RuntimeError("Both workers must be running and inspectable")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("Worker policy verification failed; inspect as ds without dumping credentials.\n")
        sys.exit(1)
