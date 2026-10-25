"""Set up the local laboratory files bucket as the production bucket is: incomplete multipart uploads are aborted after
7 days, and Odoo's key creates no bucket. Also add a bucket the key is not allowed on, so the tests can check that the
key reaches its own bucket only, and a bucket of the key's that only the reconciliation tests use, which empty it: the
test shards share this server, and reconciliation deletes the objects its database has no content of. Neither exists in
production. Running it again changes nothing.

Garage creates the bucket and the key itself as it starts (`--default-bucket`); this calls its admin API afterwards."""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ADMIN_URL = os.environ["GARAGE_ADMIN_URL"]
ADMIN_TOKEN = os.environ["GARAGE_ADMIN_TOKEN"]
ACCESS_KEY = os.environ["BUCKET_LABORATORY_ACCESS_KEY"]
BUCKET = os.environ["BUCKET_LABORATORY_NAME"]
OTHER_BUCKET = os.environ["GARAGE_OTHER_BUCKET"]
RECONCILE_BUCKET = os.environ["GARAGE_RECONCILE_BUCKET"]
ABORT_INCOMPLETE_UPLOADS_DAYS = 7


def call(endpoint, query=None, body=None):
    url = f"{ADMIN_URL}/v2/{endpoint}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method="GET" if body is None else "POST")
    request.add_header("Authorization", f"Bearer {ADMIN_TOKEN}")
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def bucket_id(alias):
    try:
        return call("GetBucketInfo", {"globalAlias": alias})["id"]
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def main():
    bucket = bucket_id(BUCKET)
    if not bucket:
        sys.exit(f"Garage has no bucket {BUCKET}; it creates it as it starts with --default-bucket.")
    call(
        "UpdateBucket",
        {"id": bucket},
        {
            "lifecycleRules": [
                {
                    "ID": "abort-incomplete-uploads",
                    "Status": "Enabled",
                    "Filter": {"Prefix": ""},
                    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": ABORT_INCOMPLETE_UPLOADS_DAYS},
                }
            ]
        },
    )
    call("UpdateKey", {"id": ACCESS_KEY}, {"deny": {"createBucket": True}})
    if not bucket_id(OTHER_BUCKET):
        call("CreateBucket", body={"globalAlias": OTHER_BUCKET})
    reconcile = bucket_id(RECONCILE_BUCKET) or call("CreateBucket", body={"globalAlias": RECONCILE_BUCKET})["id"]
    permissions = {"read": True, "write": True, "owner": False}
    call("AllowBucketKey", body={"bucketId": reconcile, "accessKeyId": ACCESS_KEY, "permissions": permissions})
    print(
        f"Bucket {BUCKET} is set up; {OTHER_BUCKET} exists without access for {ACCESS_KEY}, "
        f"and {RECONCILE_BUCKET} with read and write access for it."
    )


if __name__ == "__main__":
    main()
