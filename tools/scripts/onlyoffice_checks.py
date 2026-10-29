"""Verification of owned editor runtime, identities and network boundaries.

The controller argument supplies the selected CLI's engine operations without importing the CLI again.
"""

import hashlib
import json
import uuid
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import demo_bootstrap as bootstrap
from onlyoffice_state import SERVER_IMAGE, SERVICES, OnlyofficeError


def verify_network(controller, state, marker, environment):
    controller.resources(state)
    peers = bootstrap._resources(state["project"])["containers"]
    positive = []
    for peer in peers:
        service = bootstrap._labels(peer, "containers").get(
            "com.docker.compose.service"
        )
        port = {
            "postgres": 5432,
            "cloudbeaver": 8978,
            "garage": 3903,
            "odoo": 8069,
        }.get(service)
        if port:
            for network in peer.get("NetworkSettings", {}).get("Networks", {}).values():
                if address := network.get("IPAddress"):
                    positive.append([address, port])
    targets = list(positive)
    network = controller.inspect_resource("network", state["project"] + "_onlyoffice")
    if not network:
        raise OnlyofficeError("The owned ONLYOFFICE network is not available.")
    for entry in [
        *network.get("IPAM", {}).get("Config", []),
        *network.get("subnets", []),
    ]:
        if gateway := entry.get("Gateway", entry.get("gateway")):
            targets += [
                [gateway, int(environment.get(key, default))]
                for key, default in (
                    ("MEDILAB_ODOO_PORT", "8069"),
                    ("MEDILAB_CLOUDBEAVER_PORT", "8978"),
                    ("MEDILAB_DB_PORT", "15432"),
                    ("MEDILAB_GARAGE_ADMIN_PORT", "3903"),
                )
            ]
    targets.append(["169.254.169.254", 80])
    script = "import json,socket,sys; targets=json.load(sys.stdin); reached=[]\nfor host,port in targets:\n try:\n  s=socket.create_connection((host,port),timeout=1); s.close(); reached.append(True)\n except OSError: reached.append(False)\nprint(json.dumps({'isolated':not any(reached),'reachable':all(reached),'probes':len(targets)}))"
    # Feed probe addresses privately through a separate engine invocation, never a shell string.
    adapter_id = next(
        peer["Id"]
        for peer in peers
        if bootstrap._labels(peer, "containers").get("com.docker.compose.service")
        == "onlyoffice-adapter"
    )
    command = [
        "docker",
        "exec",
        "-i",
        adapter_id,
        "python3",
        "-c",
        script,
    ]
    gateway_id = next(
        peer["Id"]
        for peer in peers
        if bootstrap._labels(peer, "containers").get("com.docker.compose.service")
        == "onlyoffice-gateway"
    )
    control = json.loads(
        controller.run(
            ["docker", "exec", "-i", gateway_id, "python3", "-c", script],
            data=json.dumps(positive),
        ).stdout
    )
    if control.get("reachable") is not True or control.get("probes", 0) < 4:
        raise OnlyofficeError(
            "Network isolation cannot be established: the backend positive controls are unavailable."
        )
    result = controller.run(command, data=json.dumps(targets))
    report = json.loads(result.stdout)
    if report.get("isolated") is not True or report.get("probes", 0) < 4:
        raise OnlyofficeError(
            "The container provider did not enforce ONLYOFFICE network isolation; no host firewall rules were changed."
        )
    callback_script = "import http.client,json,ssl; c=http.client.HTTPSConnection('onlyoffice-gateway',7443,timeout=10,context=ssl.create_default_context(cafile='/run/onlyoffice-ca/ca.crt')); c.request('POST','/medilab/laboratory-files/callback/'+('0'*64),body=json.dumps({'status':1,'key':'0'*32}),headers={'Content-Type':'application/json'}); r=c.getresponse(); print(json.dumps({'callback_refused':r.status==403 and json.loads(r.read())=={'error':1}})); c.close()"
    callback = controller.run(
        ["docker", "exec", "-i", adapter_id, "python3", "-c", callback_script]
    )
    if json.loads(callback.stdout) != {"callback_refused": True}:
        raise OnlyofficeError(
            "The Document Server namespace did not reach the authenticated callback boundary."
        )


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def verify_runtime(controller, state, marker, environment):
    controller.verify_image(state)
    directory = controller.state_directory(state["project"], state.get("base_owner"))
    ledger = directory / "verification.json"
    bucket = json.loads((directory / "runtime.json").read_text(encoding="utf-8"))[
        "bucket"
    ]
    script = (controller.ROOT / "tools/onlyoffice/verify.py").read_text(
        encoding="utf-8"
    )
    if ledger.exists():
        controller.checked_path(ledger, private=True)
        previous = json.loads(ledger.read_text(encoding="utf-8"))
        if (
            previous.get("owner") != state["owner"]
            or previous.get("project") != state["project"]
            or previous.get("bucket") != bucket
            or not isinstance(previous.get("id"), str)
            or len(previous["id"]) != 32
            or any(character not in "0123456789abcdef" for character in previous["id"])
        ):
            raise OnlyofficeError(
                "The previous disposable verification belongs to another owner; it was not removed."
            )
        cleanup = controller.compose(
            state,
            marker,
            environment,
            "exec",
            "-T",
            "odoo",
            "python3",
            "-c",
            script,
            previous["id"],
            "cleanup",
            bucket,
            timeout=120,
        )
        if json.loads(cleanup.stdout) != {"cleaned": True}:
            raise OnlyofficeError(
                "The previous disposable conversion input could not be verified as removed."
            )
        ledger.unlink()
    origin = f"http://localhost:{state['config']['MEDILAB_ONLYOFFICE_PORT']}"
    with build_opener(ProxyHandler({}), NoRedirect).open(
        Request(origin + "/healthcheck"), timeout=10
    ) as response:
        if response.status != 200 or response.read(32) != b"true":
            raise OnlyofficeError(
                "The local editor endpoint did not return exact healthy content."
            )
    identifier = uuid.uuid4().hex
    controller.atomic_json(
        ledger,
        {
            "project": state["project"],
            "owner": state["owner"],
            "bucket": bucket,
            "id": identifier,
        },
    )
    result = controller.compose(
        state,
        marker,
        environment,
        "exec",
        "-T",
        "odoo",
        "python3",
        "-c",
        script,
        identifier,
        "convert",
        bucket,
        timeout=600,
    )
    report = json.loads(result.stdout)
    if report.get("cleaned") is True:
        ledger.unlink()
    if report != {
        "health": True,
        "conversion": True,
        "jwt": True,
        "callback_refused": True,
        "cleaned": True,
    }:
        raise OnlyofficeError(
            "The actual ONLYOFFICE conversion or callback/authentication verification failed."
        )


def actual_status(controller, state):
    peers = bootstrap._resources(state["project"])["containers"]
    services = {}
    for service in SERVICES:
        selected = [
            peer
            for peer in peers
            if bootstrap._labels(peer, "containers").get("com.docker.compose.service")
            == service
        ]
        for peer in selected:
            controller.assert_resource(peer, state, "containers")
        value = selected[0].get("State", {}) if len(selected) == 1 else {}
        health = (value.get("Health") or value.get("Healthcheck") or {}).get("Status")
        services[service] = {
            "running": value.get("Status") == "running",
            "health": health,
        }
    ready = (
        state["status"] == "completed"
        and all(value["running"] for value in services.values())
        and all(
            services[name]["health"] == "healthy"
            for name in ("onlyoffice", "onlyoffice-gateway")
        )
    )
    origin = f"http://localhost:{state['config']['MEDILAB_ONLYOFFICE_PORT']}"
    if ready:
        try:
            with build_opener(ProxyHandler({}), NoRedirect).open(
                origin + "/healthcheck", timeout=3
            ) as response:
                ready = response.status == 200 and response.read(32) == b"true"
        except OSError:
            ready = False
    return {
        "project": state["project"],
        "saved_status": state["status"],
        "services": services,
        "public_url": origin,
        "ready": ready,
    }


def verify_identity(controller, state, marker, environment):
    controller.verify_image(state)
    peers = bootstrap._resources(state["project"])["containers"]
    directory = controller.state_directory(state["project"], state.get("base_owner"))
    expected = hashlib.sha256(
        (directory / "jwt").read_text(encoding="ascii").strip().encode()
    ).hexdigest()
    script = "import hashlib,hmac,json,os,sys; expected=json.load(sys.stdin); value=os.environ.get(sys.argv[1],''); print(json.dumps({'matches':hmac.compare_digest(hashlib.sha256(value.encode()).hexdigest(),expected)}))"
    for service, variable in (
        ("onlyoffice", "JWT_SECRET"),
        ("odoo", "ONLYOFFICE_JWT_SECRET"),
    ):
        selected = [
            peer
            for peer in peers
            if bootstrap._labels(peer, "containers").get("com.docker.compose.service")
            == service
            and peer.get("State", {}).get("Status") == "running"
        ]
        if len(selected) != 1:
            raise OnlyofficeError(
                "Runtime identity cannot be checked while the editor or Odoo is stopped."
            )
        if service == "onlyoffice":
            controller.assert_resource(selected[0], state, "containers")
        output = controller.run(
            [
                "docker",
                "exec",
                "-i",
                selected[0]["Id"],
                "python3",
                "-c",
                script,
                variable,
            ],
            data=json.dumps(expected),
        )
        if json.loads(output.stdout) != {"matches": True}:
            raise OnlyofficeError(
                "The running editor and Odoo do not share the owned JWT identity."
            )
    controller.compose(
        state,
        marker,
        environment,
        "exec",
        "-T",
        "onlyoffice",
        "/bin/bash",
        "/opt/medilab/onlyoffice/healthcheck.sh",
    )


def verify_image(controller, state):
    expected = controller.inspect_resource("image", SERVER_IMAGE)
    peers = [
        peer
        for peer in controller.owned_containers(state)
        if bootstrap._labels(peer, "containers").get("com.docker.compose.service")
        == "onlyoffice"
    ]
    identity = (expected or {}).get("Id", (expected or {}).get("ID", ""))
    if (
        not identity
        or len(peers) != 1
        or peers[0].get("Image", "").removeprefix("sha256:")
        != identity.removeprefix("sha256:")
    ):
        raise OnlyofficeError(
            "The running editor image does not match the pinned Document Server digest."
        )
