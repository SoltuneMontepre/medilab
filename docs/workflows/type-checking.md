# Type checking

Check the modules and their Python tests with Pyright in `basic` mode. Every error and warning fails the check.

## Setup and commands

Run from the checkout being checked, with Git, Docker and Task available:

```sh
task dev:setup
task typecheck
task test:typecheck
```

`task typecheck:prepare` prepares typing without running Pyright. The first preparation builds the pinned production Dockerfile, installs the modules in `src/core/modules.txt` and their dependencies in a temporary PostgreSQL database, then exports the installed registry. Subsequent preparations reuse a matching build. `MEDILAB_ODOO_IMAGE` can select an existing image; preparation resolves it to its immutable image ID and checks the native method sources against the pinned Odoo checkout.

The default image tag belongs to this checkout and includes its runtime dependency/configuration inputs. Preparation does not retag another worktree's image. Its containers and network have unique names and ownership labels, publish no host ports, and use no application database, volumes or credentials. Installation, export and source verification failures fail preparation. Cleanup removes only resources whose owner label matches the run.

Generated interfaces, the annotation-only Odoo mirror and registry metadata live in `.local/typecheck/current`. Do not commit or edit them. Their input identity includes the Odoo revision, image ID, lock, configuration, module list, generator and module sources/data. Dirty or mismatched native Odoo source is refused. Changed inputs trigger regeneration; the runner also checks inputs and artifact hashes before and after analysis. It refuses missing, changed or stale output.

## Diagnostics

`task typecheck` saves `.local/typecheck/report/pyright.json`, the original Pyright JSON, its stderr and `counts.json`, grouped by rule, module, file and severity. It prints every diagnostic that fails the check and the original summary. CI uploads this directory even when analysis fails.

To choose a report directory or check a temporary diagnostic fixture:

```sh
uv --project src/core run --locked python tools/typecheck/typecheck.py --report-dir .local/typecheck/investigation
uv --project src/core run --locked python tools/typecheck/typecheck.py /absolute/path/to/case.py
```

An explicit file list replaces the source list only for that invocation. Acceptance and CI use `task typecheck` without a file list, including all module Python tests and generated interfaces. Module manifests remain excluded because Odoo reads their bare dictionaries as data.

## Model interfaces

The registry provides merged `_inherit`, delegated `_inherits`, related fields and relation targets. Generated descriptors distinguish reading and writing fields. Binary fields read as Odoo 20's `BinaryValue`; unset strings and dates can be `False`, including on new records. Literal model lookups return their model's interface, and recordset operations retain that type. Unknown literal model names fail.

Methods bind to their original source declarations; their bodies remain in the check. `Self` methods retain the receiving recordset type. Runtime defaults and business methods are not executed to infer types. Configuration defaults are read from metadata only when they are constant; uncertain values remain `object` and require validation at use.

Source models keep their native Odoo base directly visible to OdooLS and add a registry interface base under `TYPE_CHECKING`. That additional base is `object` at runtime; the runtime MRO retains the original Odoo classes. The analysis mirror represents the native `AbstractModel` alias as a nominal subclass so Pyright can order those analysis bases. Native field constructors stay under `if not TYPE_CHECKING`; the generated registry descriptor supplies their analysis type. Every method body and test stays in scope. Import generated interfaces only under `TYPE_CHECKING`: their runtime counterparts deliberately raise an error.

Use literal model constants for known models. For names obtained from registry metadata, `dynamic_model` retains the common model API. `model_as`, `record_as` and `reference_as` validate the expected model or inherited mixin at runtime. Do not use dynamic lookup helpers to bypass a misspelled literal model. For `Command` operations requiring a stored database ID, `persisted_id`/`persisted_ids` check positive integer IDs and reject booleans, missing IDs and unsaved records without conversion.

## Interrupted preparation

Normal failure cleans the owned containers and network. After process termination, inspect `.local/typecheck/prepare.lock` and the matching `.prepare-<owner>/registry/owner.json`. Confirm the recorded process has stopped before removing its lock. Inspect each recorded Docker resource's `org.medilab.typecheck.owner` label before removing it. Keep unrelated resources. Remove only that owner's staging directory, then rerun `task typecheck:prepare`; it preserves the previous published build until a replacement succeeds.

## Related documents

- [Python conventions](../conventions/python.md#type-checking)
- [Testing](../conventions/testing.md#type-checking-tests)
- [Odoo intelligence](odoo-intelligence.md)
