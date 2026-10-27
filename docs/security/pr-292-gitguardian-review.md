# PR #292 GitGuardian review

**PROPOSED FALSE POSITIVE. Incident 39039733 remains Triggered pending authorized review.**

## Finding and evidence

The [GitGuardian check](https://github.com/SoltuneMontepre/medilab/runs/121645446938) for pushed commit `590ea3140715ec001080647bf8209483ded3c8ae` reports one SonarQube Token in 96 scanned PR commits. Its occurrence link identifies line 3 of `docs/integration/evidence/171-203-230-206/approval-sync/hosted-ef3f25a.json`. The exact GitHub check output and bot discussion were read through authenticated, read-only GitHub APIs; no candidate was submitted to a credential-validation endpoint.

The detected field is `sonar_scanner_revision`. Its 40-character value is a Git commit object ID, rather than a synthetic credential, redacted placeholder or service token. Its SHA-256 fingerprint is `6ae72d0b96de8ab377cc031956903cbb655842a788ef8175a86fc2ca9097cbc1`. The candidate itself is omitted here.

Independent local verification established:

- `git cat-file -t` resolves the candidate to a commit.
- Hashing the exact Git object framing and commit bytes reproduces the candidate, independently of the evidence field's name.
- The same value is the evidence's measured remote HEAD and the recorded HEAD of all five workflow runs.
- Tracked occurrences are confined to the hosted evidence and its two linked review/acceptance documents. No tracked runtime, authentication or configuration file uses it.
- The affected evidence file was introduced by pushed commit `590ea31`; its candidate was already used as a revision reference in acceptance documentation added by `174ae78`. It therefore remains in published history as Git metadata. Removing or renaming the newest field would not clear the historical incident.

[Machine-readable proof](../integration/evidence/171-203-230-206/approval-sync/gitguardian-39039733.json) records the fingerprint, assertions and occurrence locations without reproducing the candidate.

## Reproduce without displaying the value

Run from the checkout. This reads the existing value into memory and prints only assertions and its nonreversible fingerprint:

```sh
python - <<'PY'
import hashlib
import json
import subprocess

path = "docs/integration/evidence/171-203-230-206/approval-sync/hosted-ef3f25a.json"
with open(path, encoding="utf-8") as stream:
    evidence = json.load(stream)
revision = evidence["sonar_scanner_revision"]
kind = subprocess.check_output(["git", "cat-file", "-t", revision]).strip()
body = subprocess.check_output(["git", "cat-file", "commit", revision])
framed = b"commit " + str(len(body)).encode() + b"\0" + body
assert kind == b"commit"
assert hashlib.sha1(framed, usedforsecurity=False).hexdigest() == revision
assert evidence["measured_remote_head"] == revision
assert all(run["head_sha"] == revision for run in evidence["workflows"])
print("Git commit identity and all workflow revisions: PASS")
print("SHA-256 fingerprint:", hashlib.sha256(revision.encode()).hexdigest())
PY
```

## Disposition and evidence handling

The evidence supports a false-positive recommendation based on independently reproduced Git object identity. GitGuardian's contextual classifier appears to have interpreted a bare Git object ID next to a Sonar-named field as a legacy token; the internal detector reasoning was not available through the GitHub check. No claim of credential validity or invalidity comes from a live authentication attempt.

An authorized GitGuardian reviewer must inspect [incident 39039733, occurrence 307185493](https://dashboard.gitguardian.com/workspace/690815/incidents/39039733?occurrence=307185493) and approve or reject the recommendation. No incident status, scanner configuration, exclusion, quality gate or required check was changed. The original evidence field is retained so reviewers can verify the actual reported location.

No exposed credential has been established, so no revocation, rotation or history rewrite is proposed on this evidence. Published revisions, GitHub check output and scanner caches can retain the commit ID; this does not constitute a credential leak. If owner review establishes contrary evidence, treat the value as exposed, identify the actual service owner and obtain explicit approval before rotation or any published-history cleanup.

New hosted evidence must project only needed revision, run/job identity, status and quality-gate fields. Do not persist environment values, authentication headers, credential-bearing URLs, raw service responses or raw logs. Inspect candidate values in memory and record fingerprints and boolean assertions. A passing check or this document does not authorize resolving the incident.

## Related documents

- [Integration acceptance](../integration/171-203-230-206-acceptance.md)
- [Sonar owner disposition review](pr-292-sonar-disposition-review.md)
- [Security index](readme.md)
