"""Disposable verification inside Odoo; stdout contains booleans only, never signed URLs or credentials."""

import io
import json
import os
import re
import sys
import time
import uuid
import zipfile
from urllib.parse import urlsplit, urlunsplit

import boto3
import jwt
import requests
from botocore.config import Config


def loopback_origin(value):
    try:
        parsed = urlsplit(value)
        valid = (
            isinstance(value, str)
            and parsed.scheme == "http"
            and parsed.hostname == "localhost"
            and parsed.username is None
            and parsed.password is None
            and not any((parsed.path, parsed.query, parsed.fragment))
            and parsed.port is not None
            and 1 <= parsed.port <= 65535
            and not any(
                character.isspace() or ord(character) < 32 for character in value
            )
        )
    except (AttributeError, TypeError, ValueError):
        valid = False
    if not valid:
        raise RuntimeError("Invalid owned local verification origin")
    return value


def _verification_identity(marker, cleanup, expected_bucket):
    if cleanup and marker is None:
        raise RuntimeError(
            "Cleanup requires its owned disposable verification identity"
        )
    marker = uuid.uuid4().hex if marker is None else marker
    if not isinstance(marker, str) or not re.fullmatch(r"[a-f0-9]{32}", marker):
        raise RuntimeError("Invalid disposable verification identity")
    if (
        not isinstance(expected_bucket, str)
        or not expected_bucket
        or os.environ["BUCKET_LABORATORY_NAME"] != expected_bucket
        or os.environ["BUCKET_LABORATORY_ADDRESS"] != "http://garage:3900"
        or not os.environ.get("BUCKET_LABORATORY_ACCESS_KEY")
        or not os.environ.get("BUCKET_LABORATORY_SECRET_KEY")
    ):
        raise RuntimeError(
            "The owned local Garage target differs from the running application"
        )
    return marker


def _verification_session(expected_storage_origin, expected_origin):
    if (
        os.environ["BUCKET_LABORATORY_PUBLIC_ADDRESS"]
        != loopback_origin(expected_storage_origin)
        or os.environ["ONLYOFFICE_PUBLIC_URL"] != loopback_origin(expected_origin)
        or os.environ["ONLYOFFICE_INTERNAL_URL"] != "https://onlyoffice-gateway:9443"
        or os.environ["ONLYOFFICE_CALLBACK_ORIGIN"] != "https://onlyoffice-gateway:7443"
        or os.environ.get("REQUESTS_CA_BUNDLE") != "/run/onlyoffice-trust/bundle.crt"
    ):
        raise RuntimeError(
            "The running editor endpoints differ from the owned local configuration"
        )
    internal = os.environ["ONLYOFFICE_INTERNAL_URL"]
    public = os.environ["ONLYOFFICE_PUBLIC_URL"]
    secret = os.environ["ONLYOFFICE_JWT_SECRET"]
    session = requests.Session()
    session.trust_env = False
    session.verify = "/run/onlyoffice-trust/bundle.crt"
    return session, internal, public, secret


def _wait_ready(session):
    deadline = time.monotonic() + 45
    while True:
        try:
            response = session.get(
                "http://127.0.0.1:8069/medilab/api/v1/ready",
                timeout=3,
                allow_redirects=False,
            )
            if response.status_code == 200:
                break
        except requests.RequestException:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("The local application did not become ready")
        time.sleep(0.2)


def _storage_client_options():
    return {
        "region_name": os.environ["BUCKET_LABORATORY_REGION"],
        "aws_access_key_id": os.environ["BUCKET_LABORATORY_ACCESS_KEY"],
        "aws_secret_access_key": os.environ["BUCKET_LABORATORY_SECRET_KEY"],
        "config": Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 1},
            proxies={},
        ),
    }


def _disposable_document(marker):
    document = io.BytesIO()
    with zipfile.ZipFile(document, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/document.xml",
            f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{marker}</w:t></w:r></w:p></w:body></w:document>',
        )
    return document


def _jwt_refused(session, internal, secret, conversion):
    invalid_key = "invalid-local-verification-key-0000000000"
    if secret == invalid_key:
        invalid_key += "-different"
    bad = session.post(
        internal + "/ConvertService.ashx",
        json={
            **conversion,
            "token": jwt.encode(
                conversion,
                invalid_key,
                algorithm="HS256",
            ),
        },
        headers={"Accept": "application/json"},
        timeout=15,
        allow_redirects=False,
    )
    rejected = bad.json()
    return (
        bad.status_code in {200, 403}
        and rejected.get("error") == -8
        and not rejected.get("fileUrl")
        and rejected.get("endConvert") is not True
    )


def _conversion_succeeded(session, converted, internal, public):
    payload = converted.json()
    target = urlsplit(payload.get("fileUrl", ""))
    allowed = {
        urlsplit(internal).netloc: urlsplit(internal).scheme,
        urlsplit(public).netloc: urlsplit(public).scheme,
    }
    if (
        target.netloc not in allowed
        or target.scheme != allowed[target.netloc]
        or not target.path.startswith("/cache/files/")
        or target.username
        or target.password
    ):
        raise RuntimeError("Unexpected conversion result origin")
    endpoint = urlsplit(internal)
    download = urlunsplit(
        (endpoint.scheme, endpoint.netloc, target.path, target.query, "")
    )
    pdf = session.get(download, timeout=30, allow_redirects=False)
    return (
        converted.status_code == 200
        and payload.get("endConvert") is True
        and pdf.status_code == 200
        and pdf.content.startswith(b"%PDF-")
        and len(pdf.content) > 100
    )


def _cleanup_object(storage, bucket, key):
    storage.delete_object(Bucket=bucket, Key=key)
    try:
        storage.head_object(Bucket=bucket, Key=key)
    except storage.exceptions.ClientError as error:
        if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
            return True
        raise
    return False


def verify(
    marker=None,
    cleanup=False,
    expected_bucket=None,
    expected_origin=None,
    expected_storage_origin=None,
):
    marker = _verification_identity(marker, cleanup, expected_bucket)
    result = {
        "health": False,
        "conversion": False,
        "jwt": False,
        "callback_refused": False,
        "cleaned": False,
    }
    if not cleanup:
        session, internal, public, secret = _verification_session(
            expected_storage_origin, expected_origin
        )
        _wait_ready(session)
    if not cleanup:
        answer = session.get(
            internal + "/healthcheck", timeout=5, allow_redirects=False
        )
        result["health"] = answer.status_code == 200 and answer.text == "true"
    bucket = os.environ["BUCKET_LABORATORY_NAME"]
    options = _storage_client_options()
    storage = boto3.client(
        "s3", endpoint_url=os.environ["BUCKET_LABORATORY_ADDRESS"], **options
    )
    if not cleanup:
        signer = boto3.client("s3", endpoint_url=expected_storage_origin, **options)
    key = f"onlyoffice-setup/{marker}/input.docx"
    document = _disposable_document(marker)
    try:
        if cleanup:
            return result
        storage.put_object(Bucket=bucket, Key=key, Body=document.getvalue())
        source = signer.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=300
        )
        conversion = {
            "async": False,
            "filetype": "docx",
            "outputtype": "pdf",
            "key": marker,
            "url": source,
            "title": "input.docx",
        }
        result["jwt"] = _jwt_refused(session, internal, secret, conversion)
        now = int(time.time())
        token = jwt.encode(
            {**conversion, "iat": now, "exp": now + 300}, secret, algorithm="HS256"
        )
        converted = session.post(
            internal + "/ConvertService.ashx",
            json={**conversion, "token": token},
            headers={"Accept": "application/json"},
            timeout=120,
            allow_redirects=False,
        )
        result["conversion"] = _conversion_succeeded(
            session, converted, internal, public
        )
        refusal = session.post(
            os.environ["ONLYOFFICE_CALLBACK_ORIGIN"]
            + "/medilab/laboratory-files/callback/"
            + "0" * 64,
            json={"key": marker, "status": 2},
            timeout=10,
            allow_redirects=False,
        )
        result["callback_refused"] = refusal.status_code == 403 and refusal.json() == {
            "error": 1
        }
    finally:
        result["cleaned"] = _cleanup_object(storage, bucket, key)
    return result


def main():
    cleanup = len(sys.argv) > 2 and sys.argv[2] == "cleanup"
    outcome = verify(
        sys.argv[1] if len(sys.argv) > 1 else None,
        cleanup,
        sys.argv[3] if len(sys.argv) > 3 else None,
        sys.argv[4] if len(sys.argv) > 4 else None,
        sys.argv[5] if len(sys.argv) > 5 else None,
    )
    print(json.dumps({"cleaned": outcome["cleaned"]} if cleanup else outcome))


def private_failure(_kind, _error, _traceback):
    print(
        "ONLYOFFICE disposable integration verification failed; signed request details are private.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    sys.excepthook = private_failure
    main()
