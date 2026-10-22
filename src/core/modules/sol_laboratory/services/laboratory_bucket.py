"""The laboratory files bucket: a private S3-compatible bucket used for nothing else.

Odoo calls it at its address with a key that reaches this bucket only. Computers and the editing service never get a
key, only presigned addresses on the bucket's public address. Every object is written once, under a random key the
server makes: computers upload the parts of a multipart upload the server created, and Odoo writes the documents it
stores itself, computing their size and SHA-256 as it writes them.

A database rollback undoes no call to the bucket, and Odoo runs a request again after a concurrency failure, so every
call here is safe to make twice: one that finds its work already done answers as if it had done it."""

import base64
import contextlib
import dataclasses
import datetime
import functools
import hashlib
import logging
import os
import secrets

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from odoo.http.stream import content_disposition

from odoo.addons.sol_laboratory.constants.laboratory_bucket import (
    ACCESS_KEY_VARIABLE,
    ADDRESS_VARIABLE,
    NAME_VARIABLE,
    PART_SIZE,
    PUBLIC_ADDRESS_VARIABLE,
    READ_CHUNK_SIZE,
    REGION_VARIABLE,
    SECRET_KEY_VARIABLE,
)

_logger = logging.getLogger(__name__)

# Random bytes of an object key: 32 hexadecimal digits that tell nothing about the content.
OBJECT_KEY_BYTES = 16
# Seconds to connect, and to wait for each read, on calls that do work and on the readiness check.
TIMEOUTS = {"connect_timeout": 10, "read_timeout": 120}
READY_TIMEOUTS = {"connect_timeout": 2, "read_timeout": 3}
# Failures that say nothing about the call, only that the bucket cannot be reached now.
UNREACHABLE = (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError, ConnectionClosedError)
# The bucket's codes of an upload or object that does not exist.
NO_SUCH_UPLOAD = "NoSuchUpload"
NOT_FOUND = ("404", "NoSuchKey", "NotFound")


class BucketUnavailable(Exception):
    """The bucket is not configured or cannot be reached now; the same call can succeed later."""


class UploadNotFound(Exception):
    """The multipart upload is gone: aborted, expired, or never created. Completed uploads leave their object."""


@dataclasses.dataclass(frozen=True)
class Settings:
    """How Odoo reaches the bucket, from the environment."""

    access_key: str
    secret_key: str
    name: str
    address: str
    public_address: str
    region: str


def settings():
    """The bucket's settings, or None while any of them is missing."""
    values = [
        os.environ.get(variable)
        for variable in (
            ACCESS_KEY_VARIABLE,
            SECRET_KEY_VARIABLE,
            NAME_VARIABLE,
            ADDRESS_VARIABLE,
            PUBLIC_ADDRESS_VARIABLE,
            REGION_VARIABLE,
        )
    ]
    return Settings(*values) if all(values) else None


@functools.lru_cache(maxsize=8)
def _client(bucket, endpoint, timeouts, attempts):
    # A client is costly to make and safe to share between threads, so one is kept per settings.
    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        # A checksum is sent only where the call asks for one, so presigned addresses take a plain PUT.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        retries={"mode": "standard", "max_attempts": attempts},
        **dict(timeouts),
    )
    return boto3.session.Session().client(
        "s3",
        endpoint_url=endpoint,
        region_name=bucket.region,
        aws_access_key_id=bucket.access_key,
        aws_secret_access_key=bucket.secret_key,
        config=config,
    )


def _calls():
    """The settings and the client that calls the bucket at its address."""
    bucket = settings()
    if bucket is None:
        raise BucketUnavailable("The laboratory files bucket is not configured.")
    return bucket, _client(bucket, bucket.address, tuple(TIMEOUTS.items()), 3)


def _signer():
    """The settings and the client that presigns addresses on the bucket's public address; it makes no call."""
    bucket = settings()
    if bucket is None:
        raise BucketUnavailable("The laboratory files bucket is not configured.")
    return bucket, _client(bucket, bucket.public_address, tuple(TIMEOUTS.items()), 3)


@contextlib.contextmanager
def _reaching():
    """Raise BucketUnavailable for a failure that only says the bucket cannot be reached now."""
    try:
        yield
    except UNREACHABLE as error:
        raise BucketUnavailable(f"The laboratory files bucket cannot be reached: {type(error).__name__}.") from error
    except ClientError as error:
        if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) >= 500:
            raise BucketUnavailable(f"The laboratory files bucket failed: {_code(error)}.") from error
        raise


def _code(error):
    return error.response.get("Error", {}).get("Code", "")


def _sha256_header(digest):
    return base64.b64encode(digest).decode()


def new_object_key():
    """A new random object key, which tells nothing about the content stored under it."""
    return secrets.token_hex(OBJECT_KEY_BYTES)


def is_ready():
    """True when the bucket answers with Odoo's key, within the readiness check's time limits."""
    bucket = settings()
    if bucket is None:
        return False
    client = _client(bucket, bucket.address, tuple(READY_TIMEOUTS.items()), 1)
    try:
        client.head_bucket(Bucket=bucket.name)
    except Exception as error:
        _logger.warning("The laboratory files bucket is not ready: %s", type(error).__name__)
        return False
    return True


def create_upload(key):
    """Start the multipart upload of a new object and return its upload id."""
    bucket, client = _calls()
    with _reaching():
        return client.create_multipart_upload(Bucket=bucket.name, Key=key)["UploadId"]


def part_address(key, upload_id, part_number, seconds):
    """The presigned address that uploads one part of the upload with a PUT, for seconds. It writes that part only, and
    nothing once the upload is completed or aborted."""
    bucket, signer = _signer()
    return signer.generate_presigned_url(
        "upload_part",
        Params={"Bucket": bucket.name, "Key": key, "UploadId": upload_id, "PartNumber": part_number},
        ExpiresIn=seconds,
    )


def uploaded_parts(key, upload_id):
    """The parts uploaded so far, as (number, size, ETag) in the order of their numbers."""
    bucket, client = _calls()
    parts = []
    try:
        with _reaching():
            for page in client.get_paginator("list_parts").paginate(Bucket=bucket.name, Key=key, UploadId=upload_id):
                parts += [(part["PartNumber"], part["Size"], part["ETag"]) for part in page.get("Parts", [])]
    except ClientError as error:
        if _code(error) == NO_SUCH_UPLOAD:
            raise UploadNotFound(f"The upload of {key} is gone.") from error
        raise
    return sorted(parts)


def complete_upload(key, upload_id, parts):
    """Complete the upload from its parts, as (number, ETag), and return the object's size. An upload already completed,
    such as by a request Odoo ran again, answers with its object's size."""
    return _complete(key, upload_id, [{"PartNumber": number, "ETag": etag} for number, etag in parts])


def _complete(key, upload_id, parts):
    bucket, client = _calls()
    try:
        with _reaching():
            client.complete_multipart_upload(
                Bucket=bucket.name, Key=key, UploadId=upload_id, MultipartUpload={"Parts": parts}
            )
    except ClientError as error:
        if _code(error) != NO_SUCH_UPLOAD:
            raise
    size = object_size(key)
    if size is None:
        raise UploadNotFound(f"The upload of {key} is gone and left no object.")
    return size


def abort_upload(key, upload_id):
    """Abort the upload and remove its parts. An upload already gone is left as it is."""
    bucket, client = _calls()
    try:
        with _reaching():
            client.abort_multipart_upload(Bucket=bucket.name, Key=key, UploadId=upload_id)
    except ClientError as error:
        if _code(error) != NO_SUCH_UPLOAD:
            raise


def object_size(key):
    """The size of the object, or None when it does not exist."""
    bucket, client = _calls()
    try:
        with _reaching():
            return client.head_object(Bucket=bucket.name, Key=key)["ContentLength"]
    except ClientError as error:
        if _code(error) in NOT_FOUND:
            return None
        raise


def read_address(key, seconds, filename):
    """The presigned address that reads the object with a GET, for seconds, saved under the file name."""
    bucket, signer = _signer()
    return signer.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket.name, "Key": key, "ResponseContentDisposition": content_disposition(filename)},
        ExpiresIn=seconds,
    )


@contextlib.contextmanager
def read(key):
    """The chunks of the object, from its first byte, so an object of 5 GiB is never held whole in memory."""
    bucket, client = _calls()
    with _reaching():
        body = client.get_object(Bucket=bucket.name, Key=key)["Body"]
    with contextlib.closing(body):
        yield _chunks(body)


def _chunks(body):
    with _reaching():
        yield from body.iter_chunks(READ_CHUNK_SIZE)


def write(key, chunks):
    """Write the chunks to a new object under the key, and return the size and the SHA-256 Odoo computed of them. Each
    part carries its SHA-256, which the bucket checks, so the object holds the bytes Odoo hashed. Empty content is
    written in one call, as a multipart upload has at least one part of at least one byte."""
    bucket, client = _calls()
    digest = hashlib.sha256()
    size = 0
    buffer = bytearray()
    upload_id = None
    parts = []
    try:
        for chunk in chunks:
            digest.update(chunk)
            size += len(chunk)
            buffer += chunk
            while len(buffer) >= PART_SIZE:
                if upload_id is None:
                    with _reaching():
                        upload_id = client.create_multipart_upload(
                            Bucket=bucket.name, Key=key, ChecksumAlgorithm="SHA256"
                        )["UploadId"]
                parts.append(_write_part(client, bucket, key, upload_id, len(parts) + 1, bytes(buffer[:PART_SIZE])))
                del buffer[:PART_SIZE]
        if upload_id is None:
            with _reaching():
                client.put_object(
                    Bucket=bucket.name,
                    Key=key,
                    Body=bytes(buffer),
                    ChecksumSHA256=_sha256_header(hashlib.sha256(buffer).digest()),
                )
            return size, digest.hexdigest()
        if buffer:
            parts.append(_write_part(client, bucket, key, upload_id, len(parts) + 1, bytes(buffer)))
        _complete(key, upload_id, parts)
    except BaseException:
        if upload_id is not None:
            with contextlib.suppress(Exception):
                abort_upload(key, upload_id)
        raise
    return size, digest.hexdigest()


def _write_part(client, bucket, key, upload_id, number, data):
    checksum = _sha256_header(hashlib.sha256(data).digest())
    with _reaching():
        etag = client.upload_part(
            Bucket=bucket.name, Key=key, UploadId=upload_id, PartNumber=number, Body=data, ChecksumSHA256=checksum
        )["ETag"]
    return {"PartNumber": number, "ETag": etag, "ChecksumSHA256": checksum}


def objects():
    """Every object of the bucket as (key, size, last modified as a naive UTC time), page by page in the order of their
    keys, so a bucket of any size is never held whole in memory."""
    bucket, client = _calls()
    with _reaching():
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket.name):
            for entry in page.get("Contents", []):
                yield entry["Key"], entry["Size"], _naive_utc(entry["LastModified"])


def multipart_uploads():
    """Every multipart upload of the bucket that is neither completed nor aborted, as (key, upload id, initiated as a
    naive UTC time)."""
    bucket, client = _calls()
    with _reaching():
        for page in client.get_paginator("list_multipart_uploads").paginate(Bucket=bucket.name):
            for entry in page.get("Uploads", []):
                yield entry["Key"], entry["UploadId"], _naive_utc(entry["Initiated"])


def _naive_utc(moment):
    return moment.astimezone(datetime.UTC).replace(tzinfo=None)


def read_text(key):
    """The text of a small object, or None when it does not exist."""
    bucket, client = _calls()
    try:
        with _reaching():
            return client.get_object(Bucket=bucket.name, Key=key)["Body"].read().decode()
    except ClientError as error:
        if _code(error) in NOT_FOUND:
            return None
        raise


def write_text(key, text):
    """Write a small object holding the text."""
    bucket, client = _calls()
    data = text.encode()
    with _reaching():
        client.put_object(
            Bucket=bucket.name, Key=key, Body=data, ChecksumSHA256=_sha256_header(hashlib.sha256(data).digest())
        )


def delete(key):
    """Delete the object; one already gone is left as it is."""
    bucket, client = _calls()
    with _reaching():
        client.delete_object(Bucket=bucket.name, Key=key)
