import hashlib
import socket
import urllib.parse

import requests

from odoo.tests import TransactionCase
from odoo.tests.common import _super_send

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_CONTENT
from odoo.addons.sol_laboratory.services import laboratory_bucket


def closed_port():
    """A port of this machine nothing listens on, as the address of a service that is down."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def remove_written_objects(case):
    """Delete, after the test, the objects of the contents the test records, which its rollback leaves in the bucket."""
    contents = case.env[MODEL_LABORATORY_CONTENT].sudo()
    last_id = contents.search([], order="id desc", limit=1).id

    def remove():
        for key in contents.search([("id", ">", last_id)]).mapped("object_key"):
            laboratory_bucket.delete(key)

    case.addCleanup(remove)


class LaboratoryBucketCase(TransactionCase):
    """Tests against the laboratory files bucket of local development and CI. What they write to it is theirs to
    remove."""

    @classmethod
    def _request_handler(cls, s, r, /, **kw):
        # Odoo's tests refuse requests to other hosts; the local bucket is called as computers call it.
        bucket = laboratory_bucket.settings()
        if bucket and urllib.parse.urlsplit(r.url).netloc == urllib.parse.urlsplit(bucket.address).netloc:
            return _super_send(s, r, **kw)
        return super()._request_handler(s, r, **kw)

    def bucket(self):
        """The bucket's settings, which the tests need."""
        bucket = laboratory_bucket.settings()
        if bucket is None:
            self.fail("The laboratory files bucket is not configured.")
        return bucket

    def new_key(self):
        """A new object key, whose object is deleted after the test."""
        key = laboratory_bucket.new_object_key()
        self.addCleanup(laboratory_bucket.delete, key)
        return key

    def new_upload(self, key):
        """A new multipart upload of the key, aborted after the test unless it was completed."""
        upload_id = laboratory_bucket.create_upload(key)
        self.addCleanup(laboratory_bucket.abort_upload, key, upload_id)
        return upload_id

    def call_presigned(self, method, url, data=None):
        """Call a presigned address as a computer does. It is made for the bucket's public address, which this server
        does not reach, so the call goes to the bucket's own address with the host the address was signed for."""
        address = urllib.parse.urlsplit(url)
        internal = urllib.parse.urlsplit(self.bucket().address)
        target = address._replace(scheme=internal.scheme, netloc=internal.netloc).geturl()
        return requests.request(method, target, data=data, headers={"Host": address.netloc}, timeout=60)

    def stored(self, key):
        """The SHA-256 and size of the object, read back from the bucket."""
        digest = hashlib.sha256()
        size = 0
        with laboratory_bucket.read(key) as chunks:
            for chunk in chunks:
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size
