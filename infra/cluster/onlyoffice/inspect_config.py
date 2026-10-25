"""Verify effective policy attested inside the native workers without exposing credentials."""

import hashlib
import json
import sys
from pathlib import Path

SETTINGS = Path("/opt/medilab/onlyoffice/settings.json")
REPORT_DIRECTORY = Path("/run/onlyoffice-runtime")
BINARIES = {
    "docservice": "556df4aab7b1a87123046a4459baee34e60f57deaf7bcd189bccd6f271bd8fcb",
    "converter": "ac76144203fd4e8fdee4cccac976697e87ec9b67b7bdf572e6ea1288524a8f80",
}


def selected_policy(settings):
    config = settings["services"]["CoAuthoring"]
    outbox = config["token"]["outbox"]
    return {
        "callbackRequestTimeout": config["server"]["callbackRequestTimeout"],
        "cache_files": config["expire"]["files"],
        "outbox": {
            key: outbox[key] for key in ["header", "prefix", "inBody", "algorithm", "expires", "urlExclusionRegex"]
        },
        "tlsVerification": config["requestDefaults"]["rejectUnauthorized"],
        "callbackBackoffOptions": config["callbackBackoffOptions"],
        "autoAssembly": config["autoAssembly"]["enable"],
    }


def inspect_workers(settings_path=SETTINGS, report_directory=REPORT_DIRECTORY, process_root=Path("/proc")):
    settings_bytes = settings_path.read_bytes()
    expected = json.loads(settings_bytes)
    settings_hash = hashlib.sha256(settings_bytes).hexdigest()
    reports = []
    found = set()
    for process in process_root.iterdir():
        if not process.name.isdigit():
            continue
        try:
            name = (process / "comm").read_text(encoding="utf-8").strip()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if name not in BINARIES:
            continue
        report_path = report_directory / (name + "-" + process.name + ".json")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        stat = (process / "stat").read_text(encoding="utf-8")
        start_ticks = stat[stat.rfind(")") + 2 :].split()[19]
        env = dict(value.split(b"=", 1) for value in (process / "environ").read_bytes().split(b"\0") if b"=" in value)
        if (
            report["worker"] != name
            or report["pid"] != int(process.name)
            or report["startTicks"] != start_ticks
            or report["binarySha256"] != BINARIES[name]
            or report["settingsSha256"] != settings_hash
            or report["policy"] != selected_policy(expected)
            or env.get(b"NODE_ENV") != b"production-linux"
            or env.get(b"NODE_CONFIG_DIR") != b"/etc/onlyoffice/documentserver"
            or json.loads(env[b"NODE_CONFIG"]) != expected
        ):
            raise RuntimeError("Effective worker configuration differs from the committed settings")
        reports.append(report)
        found.add(name)
    if found != set(BINARIES):
        raise RuntimeError("Both workers must be running and inspectable")
    return reports


def main():
    for report in inspect_workers():
        sys.stdout.write(json.dumps(report) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("Worker policy verification failed; inspect as ds without dumping credentials.\n")
        sys.exit(1)
