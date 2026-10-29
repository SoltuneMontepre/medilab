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


def verify(marker=None, cleanup=False, expected_bucket=None):
    marker = marker or uuid.uuid4().hex
    if not re.fullmatch(r"[a-f0-9]{32}", marker):
        raise RuntimeError("Invalid disposable verification identity")
    if (
        expected_bucket is not None
        and os.environ["BUCKET_LABORATORY_NAME"] != expected_bucket
    ):
        raise RuntimeError(
            "The selected disposable bucket differs from the running application"
        )
    result = {
        "health": False,
        "conversion": False,
        "jwt": False,
        "callback_refused": False,
        "cleaned": False,
    }
    internal = os.environ["ONLYOFFICE_INTERNAL_URL"]
    public = os.environ["ONLYOFFICE_PUBLIC_URL"]
    secret = os.environ["ONLYOFFICE_JWT_SECRET"]
    session = requests.Session()
    session.trust_env = True
    deadline = time.monotonic() + 45
    while not cleanup:
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
    if not cleanup:
        answer = session.get(
            internal + "/healthcheck", timeout=5, allow_redirects=False
        )
        result["health"] = answer.status_code == 200 and answer.text == "true"
    bucket = os.environ["BUCKET_LABORATORY_NAME"]
    options = {
        "region_name": os.environ["BUCKET_LABORATORY_REGION"],
        "aws_access_key_id": os.environ["BUCKET_LABORATORY_ACCESS_KEY"],
        "aws_secret_access_key": os.environ["BUCKET_LABORATORY_SECRET_KEY"],
        "config": Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 1},
        ),
    }
    storage = boto3.client(
        "s3", endpoint_url=os.environ["BUCKET_LABORATORY_ADDRESS"], **options
    )
    signer = boto3.client(
        "s3", endpoint_url=os.environ["BUCKET_LABORATORY_PUBLIC_ADDRESS"], **options
    )
    key = f"onlyoffice-setup/{marker}/input.docx"
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
        bad = session.post(
            internal + "/ConvertService.ashx",
            json={
                **conversion,
                "token": jwt.encode(
                    conversion,
                    "invalid-local-verification-key-0000000000",
                    algorithm="HS256",
                ),
            },
            headers={"Accept": "application/json"},
            timeout=15,
            allow_redirects=False,
        )
        rejected = bad.json()
        result["jwt"] = (
            bad.status_code in {200, 403}
            and rejected.get("error") == -8
            and not rejected.get("fileUrl")
            and rejected.get("endConvert") is not True
        )
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
        result["conversion"] = (
            converted.status_code == 200
            and payload.get("endConvert") is True
            and pdf.status_code == 200
            and pdf.content.startswith(b"%PDF-")
            and len(pdf.content) > 100
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
        storage.delete_object(Bucket=bucket, Key=key)
        try:
            storage.head_object(Bucket=bucket, Key=key)
        except storage.exceptions.ClientError as error:
            if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                result["cleaned"] = True
            else:
                raise
    return result


def main():
    cleanup = len(sys.argv) > 2 and sys.argv[2] == "cleanup"
    outcome = verify(
        sys.argv[1] if len(sys.argv) > 1 else None,
        cleanup,
        sys.argv[3] if len(sys.argv) > 3 else None,
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
