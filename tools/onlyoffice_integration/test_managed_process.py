"""Detached fake browsers cannot survive the parent deadline or launch after cancellation."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import managed_browser_exec, managed_process


@unittest.skipUnless(sys.platform == "linux", "Linux /proc and process-group contract")
class TestManagedProcess(unittest.TestCase):
    def test_nonzero_exit_cleans_detached_browser_and_refuses_foreign_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            parent = directory / "parent.py"
            parent.write_text(
                "import os,subprocess,sys,time\n"
                "from tools.onlyoffice_integration.managed_process import identity\n"
                "import json,pathlib\n"
                "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(300)'],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
                "r=identity(p.pid);r.update(nonce='a'*32,launcher_group=os.getpgrp())\n"
                "pathlib.Path(os.environ['OUTPUT']).write_text(json.dumps(r))\n"
                "sys.exit(7)\n"
            )
            environment = {
                **os.environ,
                "OUTPUT": str(directory / "browser-launch.json"),
                "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            }
            result = managed_process.run_owned(
                [sys.executable, str(parent)],
                directory=directory,
                nonce="a" * 32,
                executable=Path(sys.executable),
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(result.returncode, 7)
            self.assertTrue(result.managed_evidence["cleanup"]["forced"])
            record = json.loads((directory / "browser-launch.json").read_text())
            remaining = managed_process.identity(record["pid"])
            self.assertTrue(remaining is None or remaining["state"] == "Z")
            with subprocess.Popen(
                [sys.executable, "-c", "import time;time.sleep(300)"],
                start_new_session=True,
            ) as unrelated:
                try:
                    record = managed_process.identity(unrelated.pid)
                    record.update(nonce="a" * 32, launcher_group=unrelated.pid)
                    (directory / "browser-launch.json").write_text(json.dumps(record))
                    self.assertIsNone(
                        managed_process.browser_group(
                            directory, "a" * 32, unrelated.pid + 1, Path(sys.executable)
                        )
                    )
                    self.assertIsNone(unrelated.poll())
                finally:
                    unrelated.kill()

    def test_leader_exit_cannot_leave_same_group_child_ignoring_term(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            leader = directory / "leader.py"
            leader.write_text(
                "import json,os,pathlib,signal,subprocess,sys,time\n"
                "from tools.onlyoffice_integration.managed_process import identity\n"
                "signal.signal(signal.SIGTERM,signal.SIG_DFL)\n"
                "c=subprocess.Popen([sys.executable,'-c',\"import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print('ready',flush=True);time.sleep(300)\"],stdout=subprocess.PIPE)\n"
                "c.stdout.readline()\n"
                "r=identity(os.getpid());r.update(nonce='a'*32,launcher_group=int(os.environ['OWNER_GROUP']),child_pid=c.pid)\n"
                "pathlib.Path(os.environ['OUTPUT']).write_text(json.dumps(r))\n"
                "time.sleep(300)\n"
            )
            parent = directory / "parent.py"
            parent.write_text(
                "import os,signal,subprocess,sys,time\n"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                "os.environ['OWNER_GROUP']=str(os.getpgrp())\n"
                "p=subprocess.Popen([sys.executable,sys.argv[1]],start_new_session=True)\n"
                "p.wait();time.sleep(300)\n"
            )
            environment = {
                **os.environ,
                "OUTPUT": str(directory / "browser-launch.json"),
                "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            }
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                managed_process.run_owned(
                    [sys.executable, str(parent), str(leader)],
                    directory=directory,
                    nonce="a" * 32,
                    executable=Path(sys.executable),
                    timeout=1,
                    capture_output=True,
                    text=True,
                    env=environment,
                )
            record = json.loads((directory / "browser-launch.json").read_text())
            remaining = managed_process.identity(record["child_pid"])
            self.assertTrue(remaining is None or remaining["state"] == "Z")
            self.assertTrue(caught.exception.managed_evidence["cleanup"]["forced"])

    def test_detached_browser_ignoring_term_is_killed_and_original_timeout_retained(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            child = directory / "browser.py"
            child.write_text(
                "import json,os,pathlib,signal,time\n"
                "from tools.onlyoffice_integration.managed_process import identity\n"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                "r=identity(os.getpid());r.update(nonce='a'*32,launcher_group=int(os.environ['OWNER_GROUP']))\n"
                "pathlib.Path(os.environ['OUTPUT']).write_text(json.dumps(r))\n"
                "time.sleep(300)\n"
            )
            parent = directory / "parent.py"
            parent.write_text(
                "import os,subprocess,sys,time\n"
                "os.environ['OWNER_GROUP']=str(os.getpgrp())\n"
                "subprocess.Popen([sys.executable,sys.argv[1]],start_new_session=True)\n"
                "time.sleep(300)\n"
            )
            environment = {
                **os.environ,
                "OUTPUT": str(directory / "browser-launch.json"),
                "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            }
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                managed_process.run_owned(
                    [sys.executable, str(parent), str(child)],
                    directory=directory,
                    nonce="a" * 32,
                    executable=Path(sys.executable),
                    timeout=1,
                    capture_output=True,
                    text=True,
                    env=environment,
                )
            record = json.loads((directory / "browser-launch.json").read_text())
            evidence = caught.exception.managed_evidence
            self.assertTrue(evidence["timed_out"])
            self.assertTrue(evidence["cleanup"]["cancel_published"])
            self.assertTrue(evidence["cleanup"]["browser_identity_validated"])
            self.assertIn(record["group"], evidence["cleanup"]["groups_signalled"])
            remaining = managed_process.identity(record["pid"])
            self.assertTrue(remaining is None or remaining["state"] == "Z")

    def test_cancel_published_during_wrapper_record_prevents_chrome_exec(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nonce = "a" * 32
            directory = root / ".local/onlyoffice-managed" / nonce
            directory.mkdir(parents=True, mode=0o700)
            (directory / "manifest.json").write_text(
                json.dumps({"nonce": nonce, "status": "running"})
            )
            original_link = os.link

            def publish_and_cancel(source, target):
                original_link(source, target)
                (directory / "browser-cancel").touch(mode=0o600)

            current = managed_process.identity(os.getpid())
            current.update(group=os.getpid(), session=os.getpid())
            with (
                patch.object(managed_browser_exec, "ROOT", root),
                patch.dict(os.environ, {"MEDILAB_MANAGED_NONCE": nonce}),
                patch.object(managed_browser_exec, "identity", return_value=current),
                patch.object(
                    managed_browser_exec.os, "link", side_effect=publish_and_cancel
                ),
                patch.object(managed_browser_exec.os, "execv") as execute,
            ):
                managed_browser_exec.main()
            execute.assert_not_called()
            self.assertTrue((directory / "browser-launch.json").is_file())


if __name__ == "__main__":
    unittest.main()
