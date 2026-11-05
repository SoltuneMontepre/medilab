"""Build the jar of the plantuml-java MCP server and start the PlantUML server of plantuml-infobip.

Runs on the host from ai:plantuml and ai:plantuml-server; the taskfile passes the pinned commit, image, name and port.
Usage: ai_plantuml.py jar --directory PATH --repository URL --commit SHA --jar PATH
       ai_plantuml.py server --image IMAGE --name NAME --port PORT
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from local_private_paths import (
    LocalPrivatePathError,
    ensure_local_directory,
    guard_local_path,
)

ROOT = Path(__file__).resolve().parents[2]
JAVA_MINIMUM = 21  # plantuml-mcp builds and runs on Java 21


class PlantumlError(RuntimeError):
    pass


def java_major(text):
    """The major version in the output of java -version; Java 8 and older report themselves as 1.x."""
    match = re.search(r'version "(\d+)(?:\.(\d+))?', text)
    if not match:
        return 0
    return int(match[2]) if match[1] == "1" and match[2] else int(match[1])


def required(name, hint):
    found = shutil.which(name)
    if not found:
        raise PlantumlError(f"{name} was not found. {hint}, then reopen the terminal.")
    return found


def run(arguments, **options):
    # Child output goes to stderr, so stdout carries only the status line the task prints
    if not options.get("capture_output"):
        options.setdefault("stdout", sys.stderr)
    return subprocess.run(arguments, check=True, **options)


def build_jar(arguments):
    java = required(
        "java",
        f"Install Java {JAVA_MINIMUM} or newer, such as winget install EclipseAdoptium.Temurin.21.JDK",
    )
    version = subprocess.run(
        [java, "-version"], capture_output=True, text=True, timeout=30, check=False
    )
    if java_major(version.stderr + version.stdout) < JAVA_MINIMUM:
        raise PlantumlError(
            f"plantuml-mcp needs Java {JAVA_MINIMUM} or newer; {java} is older."
        )
    git = required("git", "Install Git")
    directory = (ROOT / arguments.directory).resolve()
    ensure_local_directory(ROOT, directory.parent)
    guard_local_path(ROOT, directory)
    if not (directory / ".git").is_dir():
        run([git, "clone", "--quiet", arguments.repository, str(directory)])
    run([git, "-C", str(directory), "fetch", "--quiet", "origin"])
    run(
        [
            git,
            "-C",
            str(directory),
            "-c",
            "advice.detachedHead=false",
            "checkout",
            "--quiet",
            arguments.commit,
        ]
    )
    # The Gradle wrapper starts through java, because Task's shell on Windows cannot run gradlew.bat
    wrapper = [
        "-cp",
        "gradle/wrapper/gradle-wrapper.jar",
        "org.gradle.wrapper.GradleWrapperMain",
    ]
    run([java, *wrapper, "bootJar", "--quiet"], cwd=directory)
    jar = ROOT / arguments.jar
    if not jar.is_file():
        raise PlantumlError(
            f"The build did not produce {arguments.jar}; check the jar name in .mcp.json."
        )
    sys.stdout.write(
        f"plantuml-java jar built in {arguments.jar}; start a new agent session.\n"
    )


def start_server(arguments):
    docker = required("docker", "Install Docker Desktop or a Docker-compatible Podman")
    if subprocess.run(
        [docker, "info"], capture_output=True, timeout=60, check=False
    ).returncode:
        raise PlantumlError(
            "The local container engine did not answer. Start Docker Desktop or the local Podman service."
        )
    inspect = subprocess.run(
        [docker, "container", "inspect", arguments.name],
        capture_output=True,
        check=False,
    )
    if inspect.returncode == 0:
        run([docker, "start", arguments.name], capture_output=True)
    else:
        port = f"127.0.0.1:{arguments.port}:8080"
        run(
            [
                docker,
                "run",
                "--detach",
                "--name",
                arguments.name,
                "--restart",
                "unless-stopped",
                "--publish",
                port,
                arguments.image,
            ],
            capture_output=True,
        )
    sys.stdout.write(f"PlantUML server at http://localhost:{arguments.port}.\n")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    jar = commands.add_parser("jar")
    for option in ("--directory", "--repository", "--commit", "--jar"):
        jar.add_argument(option, required=True)
    server = commands.add_parser("server")
    for option in ("--image", "--name", "--port"):
        server.add_argument(option, required=True)
    arguments = parser.parse_args()
    try:
        (build_jar if arguments.command == "jar" else start_server)(arguments)
    except subprocess.CalledProcessError as error:
        if error.stderr:
            sys.stderr.write(
                error.stderr
                if isinstance(error.stderr, str)
                else error.stderr.decode(errors="replace")
            )
        return error.returncode or 1
    except (
        PlantumlError,
        LocalPrivatePathError,
        OSError,
        subprocess.TimeoutExpired,
    ) as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
