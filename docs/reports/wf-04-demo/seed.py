"""Seed the samples of the WF-04 demo, or upload a file as the colleague's computer of DS-04e.

Usage:
    python seed.py [--url URL] [--db DB]
    python seed.py colleague FOLDER_ID FILE [--path NAME] [--url URL] [--db DB]

Every sample is bottled water from Green Farm compared with QCVN 6-1:2010/BYT unless stated, received in good condition,
handed to Chemistry and assigned to demo.tester. Demo users sign in with MEDILAB_DEMO_PASSWORD, or `demo`.
"""

import argparse
import datetime
import hashlib
import http.cookiejar
import json
import os
import pathlib
import time
import urllib.request
import uuid

PASSWORD = os.environ.get("MEDILAB_DEMO_PASSWORD", "demo")
RECEPTION = "demo.sample_delivery_staff"
HEAD = "demo.head_of_department"
TESTER = "demo.tester"
COLLEAGUE = "demo.chemistry_tester"
ADMINISTRATOR = "demo.administrator"
LEAD = "sol_demo.demo_test_parameter_lead"
PH = "sol_demo.demo_test_parameter_ph"
BOTTLED_WATER = ("sol_demo.demo_sample_type_bottled_water", "liquid")
LETTUCE = ("sol_demo.demo_sample_type_lettuce", "solid")
QCVN_6_1 = "sol_demo.demo_regulation_qcvn_6_1"
QCVN_8_2 = "sol_demo.demo_regulation_qcvn_8_2"


class Session:
    """A JSON-RPC session of one demo user."""

    def __init__(self, url, db, login):
        self.url = url
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.rpc("/web/session/authenticate", {"db": db, "login": login, "password": PASSWORD})

    def rpc(self, path, params):
        body = json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}).encode()
        request = urllib.request.Request(self.url + path, body, {"Content-Type": "application/json"})
        answer = json.loads(self.opener.open(request).read())
        if "error" in answer:
            raise RuntimeError(answer["error"]["data"].get("message") or answer["error"])
        return answer["result"]

    def call(self, model, method, *args, **kwargs):
        return self.rpc(
            "/web/dataset/call_kw", {"model": model, "method": method, "args": list(args), "kwargs": kwargs}
        )

    def ref(self, xmlid):
        return self.call("ir.model.data", "check_object_reference", *xmlid.split("."))[1]


def seed(url, db):
    users = {login: Session(url, db, login) for login in (RECEPTION, HEAD, TESTER, ADMINISTRATOR)}
    reception, head, tester, admin = (users[login] for login in (RECEPTION, HEAD, TESTER, ADMINISTRATOR))
    stamp = datetime.datetime.now().strftime("%d/%m %H:%M")

    # A lead measurement whose end passed holds its machine until it is marked finished, so no lead test could be booked.
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")
    held = head.call(
        "medilab.machine.booking",
        "search_read",
        [["status", "=", "in_progress"], ["ends_at", "<=", now], ["sample_test_id.parameter_id", "=", head.ref(LEAD)]],
        fields=["display_name", "machine_id"],
    )
    for booking in held:
        head.call("medilab.machine.booking", "action_done", [booking["id"]])
        print(f"Marked finished: {booking['display_name']} on {booking['machine_id'][1]}")

    def sample(label, parameters, sample_type=BOTTLED_WATER, regulation=QCVN_6_1):
        """A received sample whose tests are assigned to the tester, as {code, id, tests: {parameter: test id}}."""
        values = {
            "customer_sample_name": f"WF04 {label} {stamp}",
            "sample_type_id": reception.ref(sample_type[0]),
            "physical_state": sample_type[1],
            "test_ids": [[0, 0, {"parameter_id": reception.ref(p)}] for p in parameters],
        }
        if regulation:
            values["regulation_id"] = reception.ref(regulation)
        request = reception.call(
            "medilab.test.request",
            "create",
            {
                "customer_id": reception.ref("sol_demo.demo_customer_green_farm"),
                "committed_date": str(datetime.date.today() + datetime.timedelta(days=30)),
                "sample_ids": [[0, 0, values]],
            },
        )
        reception.call("medilab.test.request", "action_confirm", [request])
        [read] = reception.call(
            "medilab.sample", "search_read", [["request_id", "=", request]], fields=["code", "test_ids"]
        )
        reception.call("medilab.sample", "action_receive", [read["id"]], "1 chai", "good")
        head.call("medilab.sample.handover", "receive_by_label", read["code"])
        tests = admin.call("medilab.sample.test", "read", read["test_ids"], ["parameter_id"])
        tasks = admin.call(
            "medilab.task",
            "search",
            [["document_model", "=", "medilab.sample.test"], ["document_id", "in", read["test_ids"]]],
        )
        context = {"active_ids": tasks}
        wizard = head.call(
            "medilab.task.reassign", "create", {"assignee_id": head.ref("sol_demo.demo_person_tester")}, context=context
        )
        head.call("medilab.task.reassign", "action_confirm", [wizard], context=context)
        by_parameter = {p: next(t["id"] for t in tests if t["parameter_id"][0] == reception.ref(p)) for p in parameters}
        return {"label": label, "id": read["id"], "code": read["code"], "tests": by_parameter, "folders": ""}

    def book(found, parameter=LEAD, start=False):
        """The head approves the recommended booking; the tester starts it when asked, which puts the test in testing.
        A started booking whose end passes holds its machine until its result is sent, so the presenter starts the
        others."""
        test = found["tests"][parameter]
        head.call("medilab.sample.test", "action_approve_booking", [test])
        if start:
            [booking] = tester.call(
                "medilab.machine.booking", "search", [["sample_test_id", "=", test], ["status", "=", "scheduled"]]
            )
            tester.call("medilab.machine.booking", "action_start", [booking])

    def result(found, parameter, value, send=True, approve=False):
        """A result the tester enters, assessed as pass when its regulation asks, and sends."""
        test = found["tests"][parameter]
        result_id = tester.call("medilab.test.result", "create", {"sample_test_id": test, "value": value})
        [read] = tester.call("medilab.test.result", "read", [result_id], ["comparison_requested", "limit_missing"])
        if read["comparison_requested"]:
            conclusion = "insufficient" if read["limit_missing"] else "pass"
            tester.call("medilab.test.result", "write", [result_id], {"conclusion": conclusion})
        if send:
            tester.call("medilab.test.result", "action_sign", [result_id])
        if approve:
            head.call("medilab.test.result", "action_sign", [result_id])

    def folders(found, *members):
        """The sample's folders, which assigning its tests to the tester created with the tester as a member, and the
        other members, whom the administrator adds."""
        head.call("medilab.sample", "action_create_laboratory_folders", [found["id"]])
        found_folders = admin.call(
            "medilab.laboratory.folder", "search_read", [["sample_id", "=", found["id"]]], fields=["category", "root"]
        )
        for folder in found_folders:
            joined = admin.call(
                "medilab.laboratory.folder.member",
                "search_read",
                [["folder_id", "=", folder["id"]]],
                fields=["user_id"],
            )
            joined_ids = {member["user_id"][0] for member in joined}
            for login in members:
                user = admin.call("res.users", "search", [["login", "=", login]])[0]
                if user not in joined_ids:
                    admin.call(
                        "medilab.laboratory.folder.member", "create", {"folder_id": folder["id"], "user_id": user}
                    )
        found["folders"] = ", ".join(
            f"{f['root']} (id {f['id']})" for f in sorted(found_folders, key=lambda f: f["root"])
        )

    seeded = []
    a = sample("DS-04a main", [LEAD])
    book(a)
    folders(a, TESTER)
    seeded.append(a)
    b = sample("DS-04b reject and retest", [LEAD])
    book(b, start=True)
    result(b, LEAD, 0.008)
    seeded.append(b)
    c = sample("DS-04c unusual result", [LEAD])
    book(c)
    seeded.append(c)
    d = sample("DS-04d cancel", [LEAD, PH])
    book(d)
    result(d, PH, 7.2, approve=True)
    seeded.append(d)
    e = sample("DS-04e conflict", [LEAD])
    book(e)
    folders(e, TESTER, COLLEAGUE)
    seeded.append(e)
    f = sample("DS-04f file rejected", [LEAD])
    book(f)
    folders(f, TESTER)
    seeded.append(f)
    g = sample("DS-04g editor down", [LEAD])
    book(g)
    folders(g, TESTER)
    seeded.append(g)
    entry = sample("EDGE entry checks", [LEAD])
    book(entry)
    seeded.append(entry)
    withdraw = sample("EDGE withdraw", [LEAD])
    book(withdraw, start=True)
    result(withdraw, LEAD, 0.006)
    seeded.append(withdraw)
    no_limit = sample("EDGE no limit", [LEAD], sample_type=LETTUCE, regulation=QCVN_8_2)
    book(no_limit)
    seeded.append(no_limit)
    no_regulation = sample("EDGE no regulation", [LEAD], regulation=None)
    book(no_regulation)
    seeded.append(no_regulation)

    for found in seeded:
        print(f"{found['label']:<26} {found['code']:<16} {found['folders']}")


def colleague(url, db, folder_id, file, path):
    """demo.chemistry_tester's computer saves FILE as PATH in the folder, as a new version of its current one."""
    api = url + "/medilab/api/v1"
    content = pathlib.Path(file).read_bytes()

    def send(method, address, body=None, key=None):
        headers = {"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        data = json.dumps(body).encode() if body is not None else None
        with urllib.request.urlopen(urllib.request.Request(address, data, headers, method=method)) as response:
            text = response.read()
            return json.loads(text) if text else None

    signed = send(
        "POST",
        f"{api}/sign-in",
        {
            "login": COLLEAGUE,
            "password": PASSWORD,
            "client_uid": str(uuid.uuid4()),
            "name": "PC-HOA-02",
            "platform": "windows",
        },
    )
    key = signed["key"]
    files = send("GET", f"{api}/folders/{folder_id}/files", key=key)["files"]
    current = next((found["current_version"] for found in files if found["path"] == path), None)
    upload = send(
        "POST",
        f"{api}/folders/{folder_id}/uploads",
        {
            "path": path,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "base_version_id": current and current["id"],
        },
        key,
    )["upload"]
    if upload["status"] != "unchanged":
        parts = send("POST", f"{api}/folders/{folder_id}/uploads/{upload['id']}/parts", {"part_numbers": [1]}, key)
        urllib.request.urlopen(urllib.request.Request(parts["parts"][0]["url"], content, method="PUT")).close()
        send("POST", f"{api}/folders/{folder_id}/uploads/{upload['id']}/finalize", key=key)
        for _ in range(40):
            upload = send("GET", f"{api}/folders/{folder_id}/uploads/{upload['id']}", key=key)["upload"]
            if upload["status"] in ("completed", "conflict", "unchanged", "failed", "refused"):
                break
            time.sleep(0.25)
    send("POST", f"{api}/sign-out", key=key)
    print(f"{path}: {upload['status']}, version {upload.get('version') and upload['version'].get('number')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8069")
    parser.add_argument("--db", default="medilab")
    commands = parser.add_subparsers(dest="command")
    upload_parser = commands.add_parser("colleague")
    upload_parser.add_argument("folder_id", type=int)
    upload_parser.add_argument("file")
    upload_parser.add_argument("--path", help="the name in the folder; the file's own name by default")
    arguments = parser.parse_args()
    if arguments.command == "colleague":
        colleague(
            arguments.url,
            arguments.db,
            arguments.folder_id,
            arguments.file,
            arguments.path or pathlib.Path(arguments.file).name,
        )
    else:
        seed(arguments.url, arguments.db)
