"""Odoo Language Server (OdooLS) adapter for Serena.

Serena loads this module through the `solidlsp.language_server_registration` entry point;
the `odoo` key in `.serena/project.yml` turns it on. `task ai:odoo-ls` downloads the server,
and `odools.toml` at the repository root holds the Odoo paths.
"""

import logging
import os
import threading
from pathlib import Path

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import (
    ExternalLanguageServerId,
    FilenameMatcher,
    LanguageServerConfig,
    LanguageServerRegistry,
)
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

INDEXING_TIMEOUT_SECONDS = 600


def find_server_directory(repository_root_path: str) -> Path:
    """Find `.local/odoo-ls` from the project root upwards, so worktrees inside the repository share one download."""
    for directory in (Path(repository_root_path), *Path(repository_root_path).parents):
        candidate = directory / ".local" / "odoo-ls"
        if candidate.is_dir():
            return candidate
    raise RuntimeError(f"No .local/odoo-ls found from {repository_root_path} upwards; run `task ai:odoo-ls`.")


class OdooLanguageServer(SolidLanguageServer):
    """Run `odoo_ls_server` over stdio; it understands `_inherit`, model names in strings, domains, `@api.depends` and XML."""

    def __init__(
        self,
        config: LanguageServerConfig,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        """Build the server command; typeshed must sit next to the binary, as `task ai:odoo-ls` unpacks it."""
        server_directory = find_server_directory(repository_root_path)
        executable_name = "odoo_ls_server.exe" if os.name == "nt" else "odoo_ls_server"
        executable_path = server_directory / executable_name
        if not executable_path.is_file():
            raise RuntimeError(f"{executable_path} not found; run `task ai:odoo-ls`.")
        logs_directory = server_directory / "logs"
        logs_directory.mkdir(exist_ok=True)
        # The server logs at trace level by default, which grows quickly.
        command = [
            str(executable_path),
            "--log-level",
            "info",
            "--logs-directory",
            str(logs_directory),
        ]
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=command, cwd=repository_root_path),
            "python",
            solidlsp_settings,
        )
        self.indexing_complete = threading.Event()

    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        """OdooLS tells Python and XML documents apart by the languageId of didOpen."""
        return "xml" if relative_file_path.endswith(".xml") else "python"

    def _supports_pull_diagnostics(self) -> bool:
        """OdooLS panics on requests it does not handle, such as `textDocument/diagnostic`; use publishDiagnostics only."""
        return False

    def request_rename_symbol_edit(self, relative_file_path: str, line: int, column: int, new_name: str):
        """OdooLS has no rename and panics on the request, so refuse it before sending."""
        raise RuntimeError(
            "OdooLS does not support rename; rename the field or model by hand and check references in strings and XML."
        )

    def _create_base_initialize_params(self) -> dict:
        """Declare the client capabilities; Serena fills in workspaceFolders and rootUri."""
        return {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "declaration": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "configuration": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
                "window": {"workDoneProgress": True},
            },
        }

    def _start_server(self) -> None:
        """Start the server, answer the requests it needs and wait for indexing before taking queries."""

        def accept_request(params: object) -> None:
            """Answer server requests with success; OdooLS panics when registerCapability gets an error."""
            return

        def answer_configuration(params: dict) -> list[dict]:
            """Leave selectedProfile empty so the server uses the "default" profile in odools.toml."""
            return [{} for _ in params.get("items", [])]

        def do_nothing(params: object) -> None:
            """Ignore notifications that need no handling."""
            return

        def log_message(message: dict) -> None:
            """Forward server log messages to the Serena log."""
            log.info("OdooLS: %s", message.get("message", message))

        def update_loading_status(status: object) -> None:
            """Mark indexing as done when the server reports `stop`."""
            log.info("OdooLS loading status: %s", status)
            if status == "stop":
                self.indexing_complete.set()

        def report_invalid_python_path(params: object) -> None:
            """Warn when the server cannot run Python to read sys.path."""
            log.warning("OdooLS cannot run python_path: %s", params)

        def report_crash(params: object) -> None:
            """Log a crash the server reports before its process exits."""
            log.error("OdooLS crash: %s", params)

        self.server.on_request("client/registerCapability", accept_request)
        self.server.on_request("window/workDoneProgress/create", accept_request)
        self.server.on_request("window/showMessageRequest", accept_request)
        self.server.on_request("workspace/configuration", answer_configuration)
        self.server.on_notification("window/logMessage", log_message)
        self.server.on_notification("window/showMessage", log_message)
        self.server.on_notification("$/progress", do_nothing)
        # Serena stores diagnostics before calling the handler; registering it avoids "Unhandled method" logs.
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("$Odoo/setPid", do_nothing)
        self.server.on_notification("$Odoo/setConfiguration", do_nothing)
        self.server.on_notification("$Odoo/loadingStatusUpdate", update_loading_status)
        self.server.on_notification("$Odoo/invalid_python_path", report_invalid_python_path)
        self.server.on_notification("Odoo/displayCrashNotification", report_crash)

        self.server.start()
        self.server.send.initialize(self._create_initialize_params())
        self.server.notify.initialized({})
        if not self.indexing_complete.wait(timeout=INDEXING_TIMEOUT_SECONDS):
            log.warning(
                "OdooLS did not finish indexing after %s seconds; results may be incomplete.", INDEXING_TIMEOUT_SECONDS
            )


def register() -> None:
    """Entry point: register the `odoo` key for Python and XML files."""
    LanguageServerRegistry.get_instance().register(
        ExternalLanguageServerId(
            key="odoo",
            matcher=FilenameMatcher(".py", ".xml"),
            implementation=OdooLanguageServer,
        )
    )
