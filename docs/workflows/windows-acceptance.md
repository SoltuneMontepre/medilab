# Native Windows 11 setup acceptance

Use native Windows PowerShell 5.1 or PowerShell 7 to collect reproducible evidence for the root setup workflow. A Windows Server CI run checks the collector's refusal and quoting contracts; it does not establish Windows 11 acceptance. The desktop UI requires a separate acceptance session.

## Prepare a separate worktree

Install the [host prerequisites](../../README.md#prerequisites) yourself and select Docker Desktop's local Linux container engine. The collector does not install or upgrade tools, elevate privileges, start a VM, select credentials, or change the user's Sync profile and keyring.

Create a clean, linked Git worktree for the revision under test. Its absolute path must contain both a space and a non-ASCII character, for example a directory named `MediLab kiểm tra`. Create the worktree explicitly with Git; the collector never creates or deletes one. Keep committed source defaults in place. Do not copy local `.env`, private Doppler configuration, bootstrap selections, ONLYOFFICE material or Sync development metadata into it. Untracked configuration and all local ownership metadata are refused. Both its normal project namespace and its deterministic fresh project namespace must have no existing container, network or volume resources.

From that worktree, run the read-only Doctor first:

```powershell
& .\tools\scripts\windows_acceptance.ps1
```

This prints JSON and exits nonzero if the required native host, tooling or local container engine cannot be verified. Doctor does not initialize the project, compile a Rust program, create an evidence directory or claim acceptance. It refuses Windows Server, Windows 10, non-Windows hosts and unsupported PowerShell versions before invoking Task. A compatible Rust toolchain must already exist: implicit rustup toolchain installation is disabled in child processes.

## Run the acceptance sequence

After reviewing the empty-worktree preconditions, explicitly authorize initialization:

```powershell
& .\tools\scripts\windows_acceptance.ps1 -RunSetup
```

RunSetup executes these commands in order and stops at the first failure:

1. `task setup` to create the fresh project.
2. `task setup` again to verify repeatability.
3. `task onlyoffice:verify` for the real conversion and refusal checks.
4. `task sync:test`.
5. `task sync:lint`.
6. `task sync:check`.
7. `task sync:build` to produce the native NSIS package.

Child processes receive the existing host-tool environment allowlist and a private empty dotenv override. Caller credentials and application settings are excluded. Git Bash/MSYS tool directories are removed from the child PATH; private `bash.cmd` and `sh.cmd` guards fail if a command attempts to invoke an external shell. The caller's environment remains unchanged.

The collector freezes the Git revision and tracked source fingerprints. After the first setup it waits, using read-only checks, for the owned bucket's database marker to match the actual database UUID and for the exact thirteen-object demo baseline. This wait does not invoke cron, create the marker or ignore unexpected objects. A foreign marker is a failure. Every following stage must preserve the database file/version fingerprints, all bucket object contents, the managed JWT, certificate and cache-signing fingerprints, and all seven configured persistent volume identities.

A successful result has `status: passed` and `acceptance: passed`. The result records the native host and tool versions, completed command exit codes, immutable fingerprints and the NSIS package hash. It always reports `gui_acceptance: unverified`: it does not launch the desktop app or prove sign-in, tray behavior or credential-store behavior.

## Retain and interpret evidence

RunSetup writes private local evidence beneath `.local/windows-acceptance/<run-id>/` and prints its relative JSON path. Command logs stay in this directory. JSON retains each stage's actual snapshot and the sections that differ from baseline before reporting an integrity failure. A failed command also attempts a diagnostic snapshot; failure of that read does not replace the command's original exit code. JSON includes hashes and counts, not document bodies, object keys, raw secrets, signed URLs, full environment variables or full container inspection output. Do not publish or automatically archive the command logs; review any evidence before sharing it.

A failed command, source change, integrity mismatch or unavailable prerequisite produces a nonzero exit and `acceptance: unverified`. Existing resources, files, keys, configuration and logs are retained. An interrupted command's own process tree is stopped where possible; the collector does not stop or remove project containers, volumes or networks. Inspect the private evidence and fix the cause before creating another explicitly empty worktree. There is no automatic reset, deletion, credential regeneration or state repair.

## Validate the collector without accepting Windows 11

The portable contracts run without a runtime:

```powershell
python -B -m unittest discover -s tools/scripts -p 'test_*acceptance*.py' -v
```

On Windows Server, the native contract invokes both PowerShell 5.1 and PowerShell 7 from a Unicode path containing spaces. It requires each Doctor and RunSetup invocation to return blocked JSON without touching Task or the temporary project tree. A Linux skip of this native contract is not evidence of PowerShell correctness. Only a direct, successful RunSetup session on Windows 11 establishes this workflow's Windows 11 CLI acceptance.

**Related documents**

- [Setting up](setting-up.md)
- [ONLYOFFICE local runbook](../infrastructure/onlyoffice.md)
- [Testing conventions](../conventions/testing.md)
