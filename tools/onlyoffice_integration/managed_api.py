"""Normal user/API operations and independent saved-byte assertions for the managed browser probe."""

import hashlib
import io
import re
import time
import zipfile
from urllib.parse import urlsplit
from xml.etree import ElementTree

from .managed_http import HttpSession

DEVICE_NAME_PREFIX = "Managed browser "


class ProbeError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ProbeError(message)


def validate_new_device(device, nonce, existing_ids):
    identifier = device.get("id")
    require(
        type(identifier) is int
        and identifier > 0
        and identifier not in existing_ids
        and device.get("name") == DEVICE_NAME_PREFIX + nonce
        and device.get("platform") == "linux"
        and device.get("status") == "signed_in"
        and device.get("current") is True
        and ("client_uid" not in device or device["client_uid"] == nonce),
        "The sign-in answer is not the new manifested test device; revocation is forbidden.",
    )
    return identifier


def storage_url(url, origin, bucket):
    target, expected = urlsplit(url), urlsplit(origin)
    require(
        target.scheme == expected.scheme
        and target.netloc == expected.netloc
        and not target.username
        and not target.password
        and not target.fragment
        and target.path.startswith(f"/{bucket}/")
        and not any(ord(character) < 32 for character in url),
        "The API returned a foreign storage destination.",
    )
    return url


def docx_text(content):
    require(
        len(content) <= 10 * 1024 * 1024, "The test document exceeds its bounded size."
    )
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        require(
            sum(item.file_size for item in archive.infolist()) <= 25 * 1024 * 1024,
            "The test document exceeds its expanded size bound.",
        )
        tree = ElementTree.fromstring(archive.read("word/document.xml"))
    return "".join(
        node.text or ""
        for node in tree.iter(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
        )
    )


def assert_saved(initial, versions, content, marker, user_id):
    require(
        len(versions) == 2, "The real edit did not produce exactly one new version."
    )
    latest, previous = versions
    require(previous == initial, "The original immutable test version changed.")
    require(
        latest["number"] == 2
        and latest["parent_version_id"] == initial["id"]
        and latest["source"] == "edited_online"
        and latest["saved_by"]["id"] == user_id
        and latest["sha256"] != initial["sha256"]
        and latest["sha256"] == hashlib.sha256(content).hexdigest()
        and latest["size"] == len(content),
        "The persisted edit has incorrect bytes, lineage, source or attribution.",
    )
    require(
        marker in docx_text(content),
        "The saved Office XML does not contain the keyboard marker.",
    )
    return {
        "version_id": latest["id"],
        "sha256": latest["sha256"],
        "size": len(content),
        "saved_by": user_id,
    }


class ManagedApi:
    def __init__(self, base, storage, bucket, login, password):
        self.base, self.storage, self.bucket = base, storage, bucket
        self.login, self.password = login, password
        self.http = HttpSession()
        self.bytes_http = HttpSession()
        self.key = None

    def request(self, method, path, body=None, *, authenticated=True, idempotency=None):
        headers = {}
        if authenticated:
            require(bool(self.key), "The probe has no owned API device.")
            headers["Authorization"] = "Bearer " + self.key
        if idempotency:
            headers["Idempotency-Key"] = idempotency
        response = self.http.request(
            method,
            self.base + "/medilab/api/v1" + path,
            json_body=body,
            headers=headers,
            timeout=20,
            allow_redirects=False,
        )
        require(
            response.status_code in (200, 201, 202, 204),
            f"The normal business API refused the probe operation (HTTP {response.status_code}).",
        )
        return response.json() if response.content else None

    def sign_in(self, nonce, user_id):
        existing = self.devices(user_id)
        require(
            all(row["client_uid"] != nonce for row in existing),
            "The planned client identity already exists; signing in could rotate its key.",
        )
        result = self.request(
            "POST",
            "/sign-in",
            {
                "login": self.login,
                "password": self.password,
                "client_uid": nonce,
                "name": DEVICE_NAME_PREFIX + nonce,
                "platform": "linux",
            },
            authenticated=False,
        )
        identifier = validate_new_device(
            result["device"], nonce, {row["id"] for row in existing}
        )
        actual = [row for row in self.devices(user_id) if row["id"] == identifier]
        require(
            len(actual) == 1
            and actual[0]["client_uid"] == nonce
            and actual[0]["name"] == DEVICE_NAME_PREFIX + nonce
            and actual[0]["platform"] == "linux"
            and actual[0]["status"] == "signed_in",
            "Read-only server state does not confirm the owned device; revocation is forbidden.",
        )
        self.key = result["key"]
        return identifier

    def browser_session(self):
        response = self.http.get(
            self.base + "/web/login", timeout=20, allow_redirects=False
        )
        require(response.status_code == 200, "The normal login page is unavailable.")
        token = re.search(
            r'csrf_token: "([^"]+)"|name="csrf_token" value="([^"]+)"', response.text
        )
        require(token is not None, "The normal login page has no CSRF token.")
        response = self.http.post(
            self.base + "/web/login",
            data={
                "login": self.login,
                "password": self.password,
                "csrf_token": token.group(1) or token.group(2),
            },
            timeout=20,
            allow_redirects=False,
        )
        require(response.status_code in (302, 303), "The observer login was refused.")
        result = self.http.post(
            self.base + "/web/session/get_session_info",
            json_body={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {},
            },
            timeout=20,
        ).json()
        require(
            "error" not in result and result["result"]["username"] == self.login,
            "The observer actor differs.",
        )
        return result["result"]["uid"]

    def sessions(self, file_id):
        return self.read_rows(
            "medilab.laboratory.editing.session",
            [["file_id", "=", file_id]],
            [
                "status",
                "file_id",
                "opened_by_id",
                "base_version_id",
                "committed_version_id",
            ],
        )

    def devices(self, user_id):
        return self.read_rows(
            "medilab.laboratory.device",
            [["user_id", "=", user_id]],
            ["client_uid", "name", "platform", "status"],
        )

    def read_rows(self, model, domain, fields):
        result = self.http.post(
            self.base + f"/web/dataset/call_kw/{model}/search_read",
            json_body={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "model": model,
                    "method": "search_read",
                    "args": [domain],
                    "kwargs": {"fields": fields},
                },
            },
            timeout=20,
            allow_redirects=False,
        ).json()
        require("error" not in result, "The read-only session observation was refused.")
        return result["result"]

    def upload(self, folder, data, nonce, checkpoint):
        upload = self.request(
            "POST",
            f"/folders/{folder}/uploads",
            {
                "path": "managed-proof.docx",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
            idempotency=nonce + "-upload",
        )["upload"]
        checkpoint(upload_id=upload["id"])
        require(
            upload["part_count"] == 1,
            "The fixed DOCX must fit one ordinary upload part.",
        )
        parts = self.request(
            "POST",
            f"/folders/{folder}/uploads/{upload['id']}/parts",
            {"part_numbers": [1]},
        )["parts"]
        require(
            len(parts) == 1 and parts[0]["number"] == 1,
            "The API returned unexpected upload parts.",
        )
        url = storage_url(parts[0]["url"], self.storage, self.bucket)
        response = self.bytes_http.put(
            url, data=data, timeout=30, allow_redirects=False
        )
        require(
            response.status_code == 200,
            "The owned fixture part was not accepted by storage.",
        )
        self.request("POST", f"/folders/{folder}/uploads/{upload['id']}/finalize")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            current = self.request("GET", f"/folders/{folder}/uploads/{upload['id']}")[
                "upload"
            ]
            if current["status"] == "completed":
                return current["version"]
            require(
                current["status"] in ("prepared", "verifying"),
                "The owned upload ended without a version.",
            )
            time.sleep(1)
        raise ProbeError("Normal background upload verification exceeded its deadline.")

    def download(self, folder, file_id, version_id):
        url = self.request(
            "POST", f"/folders/{folder}/files/{file_id}/versions/{version_id}/download"
        )["url"]
        response = self.bytes_http.get(
            storage_url(url, self.storage, self.bucket),
            timeout=30,
            allow_redirects=False,
        )
        require(
            response.status_code == 200,
            "The persisted version was not downloadable from storage.",
        )
        return response.content
