"""Read fingerprints from one verified, completed fresh project; never emit document or secret contents."""

import hashlib
import json
import re
import subprocess
import time
import uuid

import demo_bootstrap as bootstrap
import local_compose
import onlyoffice_state

BUCKET_SNAPSHOT = r"""
import hashlib,json,os,sys,boto3
from botocore.config import Config
def private_failure(*_args):
 print('The owned storage fingerprint could not be read.',file=sys.stderr)
sys.excepthook=private_failure
expected=json.load(sys.stdin)
if (os.environ.get('BUCKET_LABORATORY_ADDRESS')!='http://garage:3900' or
 os.environ.get('BUCKET_LABORATORY_NAME')!=expected['bucket'] or
 not os.environ.get('BUCKET_LABORATORY_ACCESS_KEY') or not os.environ.get('BUCKET_LABORATORY_SECRET_KEY')):
 raise ValueError('Owned storage configuration is invalid.')
client=boto3.client('s3',endpoint_url='http://garage:3900',region_name=os.environ['BUCKET_LABORATORY_REGION'],
 aws_access_key_id=os.environ['BUCKET_LABORATORY_ACCESS_KEY'],aws_secret_access_key=os.environ['BUCKET_LABORATORY_SECRET_KEY'],
 config=Config(signature_version='s3v4',s3={'addressing_style':'path'},connect_timeout=3,read_timeout=10,
 retries={'max_attempts':0},proxies={}))
records=[]
marker={'present':False,'matches_database':False}
for page in client.get_paginator('list_objects_v2').paginate(Bucket=expected['bucket']):
 for row in page.get('Contents',[]):
  digest=hashlib.sha256()
  marker_bytes=b''
  with client.get_object(Bucket=expected['bucket'],Key=row['Key'])['Body'] as body:
   while chunk:=body.read(65536):
    digest.update(chunk)
    if row['Key']=='.medilab-database':
     marker_bytes+=chunk
     if len(marker_bytes)>128: raise ValueError('Owned storage marker is invalid.')
  records.append([row['Key'],row['Size'],digest.hexdigest()])
  if row['Key']=='.medilab-database':
   marker={'present':True,'matches_database':marker_bytes.decode().strip()==expected['database_uuid'],
           'sha256':digest.hexdigest(),'bytes':len(marker_bytes)}
print(json.dumps({'objects':len(records),'sha256':hashlib.sha256(json.dumps(sorted(records)).encode()).hexdigest(),
 'owner_marker':marker}))
"""
FILE_QUERY = (
    "SELECT id,folder_id,current_version_id,path,path_key FROM medilab_laboratory_file"
)
VERSION_QUERY = (
    "SELECT id,file_id,number,parent_version_id,restored_from_id,content_id,user_id,device_id,"
    "document_version,idempotency_key,source,sha256,approval_state,size FROM medilab_laboratory_file_version"
)


class SnapshotError(RuntimeError):
    pass


def output(arguments, *, data=None):
    result = subprocess.run(
        arguments,
        input=data,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise SnapshotError("An owned read-only fingerprint operation failed.")
    return result.stdout


def selected(project, owner):
    actual, marker, _files, _environment = local_compose._resolve("ps")
    if (
        actual != project
        or not marker
        or marker.get("status") != "completed"
        or marker.get("owner") != owner
    ):
        raise SnapshotError("The selected fresh project or owner changed.")
    if bootstrap._assert_local_engine() != marker.get("engine"):
        raise SnapshotError("The selected local engine changed.")
    resources = bootstrap._resources(project)
    containers = {}
    for service in ("postgres", "odoo", "onlyoffice"):
        peers = [
            peer
            for peer in resources["containers"]
            if bootstrap._labels(peer, "containers").get("com.docker.compose.service")
            == service
        ]
        if (
            len(peers) != 1
            or bootstrap._labels(peers[0], "containers").get(bootstrap.OWNER_LABEL)
            != owner
            or peers[0].get("State", {}).get("Running") is not True
            or not re.fullmatch(r"[a-f0-9]{64}", peers[0].get("Id", ""))
        ):
            raise SnapshotError(
                "A required owned source service is missing, stopped or ambiguous."
            )
        containers[service] = peers[0]["Id"]
    return marker, resources, containers


def database_read(container, query):
    return output(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "root",
            "-d",
            "medilab",
            "-Atqc",
            "BEGIN READ ONLY; " + query + "; ROLLBACK;",
        ]
    ).strip()


def capture(project, owner):
    marker, resources, containers = selected(project, owner)
    database_uuid = database_read(
        containers["postgres"],
        "SELECT value FROM ir_config_parameter WHERE key='database.uuid'",
    )
    try:
        canonical_uuid = str(uuid.UUID(database_uuid))
    except (ValueError, TypeError, AttributeError):
        canonical_uuid = None
    if canonical_uuid != database_uuid:
        raise SnapshotError("The owned database UUID could not be verified.")
    data = {}
    for name, query in (("files", FILE_QUERY), ("versions", VERSION_QUERY)):
        rows = json.loads(
            database_read(
                containers["postgres"],
                "SELECT COALESCE(json_agg(x ORDER BY id),'[]') FROM (" + query + ") x",
            )
        )
        data[name] = {
            "rows": len(rows),
            "sha256": hashlib.sha256(
                json.dumps(rows, sort_keys=True).encode()
            ).hexdigest(),
        }
    state = onlyoffice_state.read_state(project, marker, marker["engine"])
    if not state or state["status"] != "completed":
        raise SnapshotError("The owned editing service is not completed.")
    directory = onlyoffice_state.state_directory(project, owner)
    runtime = json.loads(
        onlyoffice_state.checked_path(directory / "runtime.json").read_text(
            encoding="utf-8"
        )
    )
    from onlyoffice import runtime_config

    if runtime != runtime_config(
        state, bootstrap._compose_environment(project, owner, marker["config"])
    ):
        raise SnapshotError("The owned runtime endpoints changed.")
    bucket = json.loads(
        output(
            [
                "docker",
                "exec",
                "-i",
                containers["odoo"],
                "python3",
                "-c",
                BUCKET_SNAPSHOT,
            ],
            data=json.dumps(
                {"bucket": runtime["bucket"], "database_uuid": database_uuid}
            ),
        )
    )
    identities = {}
    for relative in (
        "jwt",
        "tls/ca.key",
        "tls/server/tls.key",
        "tls/server/tls.crt",
        "tls/public/ca.crt",
        "tls/public/bundle.crt",
        "tls/public-roots.json",
        "runtime.json",
    ):
        path = onlyoffice_state.checked_path(
            directory / relative, private=relative.endswith(".key") or relative == "jwt"
        )
        identities[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    digest = output(
        [
            "docker",
            "exec",
            containers["onlyoffice"],
            "sha256sum",
            "/var/www/onlyoffice/Data/.private/medilab-secure-link-secret",
        ]
    ).split()[0]
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise SnapshotError(
            "The owned cache-signing fingerprint could not be verified."
        )
    identities["cache-signing-key"] = digest
    expected = {
        value for key, value in marker["config"].items() if key.endswith("_VOLUME")
    }
    if len(expected) != 7:
        raise SnapshotError(
            "The completed demo must own exactly seven configured volumes."
        )
    volumes = {}
    for volume in resources["volumes"]:
        name = volume.get("Name") or volume.get("name")
        if name in expected:
            labels = bootstrap._labels(volume, "volumes")
            if (
                labels.get(bootstrap.OWNER_LABEL) != owner
                or volume.get("Name") != name
                or not isinstance(volume.get("CreatedAt"), str)
                or not volume["CreatedAt"]
                or name in volumes
            ):
                raise SnapshotError("A persistent volume belongs to another owner.")
            volumes[name] = {
                key: volume.get(key) for key in ("Name", "CreatedAt", "Labels")
            }
    if set(volumes) != expected:
        raise SnapshotError("A required persistent volume is missing.")
    return {
        "project": project,
        "owner": owner,
        "data": data,
        "bucket": bucket,
        "private_identity_hashes": identities,
        "volumes": volumes,
    }


def ready_baseline(project, owner, *, timeout=300):
    deadline = time.monotonic() + timeout
    while True:
        snapshot = capture(project, owner)
        marker = snapshot["bucket"]["owner_marker"]
        if marker["present"] and not marker["matches_database"]:
            raise SnapshotError(
                "The bucket belongs to another database; no initialization was attempted."
            )
        if marker["present"] and snapshot["bucket"]["objects"] == 13:
            return snapshot
        if time.monotonic() >= deadline:
            raise SnapshotError(
                "The exact owned thirteen-object baseline did not become ready before the deadline."
            )
        time.sleep(1)
