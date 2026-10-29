"""A fixture must not route through a host, published port, extra network or unowned peer."""

import copy
import unittest

from .isolation import validate_plan, validate_runtime

PROJECT = "medilab-onlyoffice-isolation-test"
NETWORK = PROJECT + "_default"
METADATA = {
    "Name": NETWORK,
    "Internal": True,
    "Driver": "bridge",
    "Options": {"isolate": "strict"},
    "Labels": {"com.docker.compose.project": PROJECT},
}
MEMBER = {
    "Name": "/fixture",
    "Config": {"Labels": {"com.docker.compose.project": PROJECT}},
    "HostConfig": {"NetworkMode": "bridge", "PortBindings": {}},
    "NetworkSettings": {"Networks": {NETWORK: {}}, "Ports": {"80/tcp": None}},
    "Mounts": [],
}


class TestFixtureIsolation(unittest.TestCase):
    def test_owned_internal_network_with_no_host_publications(self):
        self.assertTrue(validate_runtime(PROJECT, METADATA, [MEMBER])["internal"])
        alternate = {
            "name": NETWORK,
            "internal": True,
            "driver": "bridge",
            "options": {"isolate": "strict"},
            "labels": METADATA["Labels"],
        }
        self.assertTrue(validate_runtime(PROJECT, alternate, [MEMBER])["internal"])
        helper = copy.deepcopy(MEMBER)
        helper["Config"]["Labels"] = {"medilab.integration.project": PROJECT}
        self.assertTrue(validate_runtime(PROJECT, METADATA, [helper])["internal"])

    def test_noninternal_external_or_unowned_network_is_refused(self):
        for changes in (
            {"Internal": False},
            {"Internal": None},
            {"Name": "other"},
            {"Labels": {}},
            {"Driver": "host"},
            {"Options": {}},
            {"Options": {"isolate": "false"}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_runtime(PROJECT, METADATA | changes, [MEMBER])
        with self.assertRaises(ValueError):
            validate_runtime(PROJECT, METADATA, [])

    def test_peers_cannot_publish_bridge_or_use_privileged_namespaces(self):
        for field, value in (
            ("NetworkMode", "host"),
            ("PidMode", "host"),
            ("Privileged", True),
            ("PortBindings", {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}),
            ("CapAdd", ["NET_ADMIN"]),
            ("CapAdd", ["CAP_SYS_ADMIN"]),
            ("CapAdd", ["ALL"]),
        ):
            member = copy.deepcopy(MEMBER)
            member["HostConfig"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_runtime(PROJECT, METADATA, [member])
        for section, field, value in (
            ("Config", "Labels", {}),
            ("NetworkSettings", "Networks", {NETWORK: {}, "outside": {}}),
            ("NetworkSettings", "Ports", {"80/tcp": [{"HostPort": "8080"}]}),
        ):
            member = copy.deepcopy(MEMBER)
            member[section][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_runtime(PROJECT, METADATA, [member])
        member = copy.deepcopy(MEMBER)
        member["Mounts"] = [{"Destination": "/var/run/docker.sock"}]
        with self.assertRaises(ValueError):
            validate_runtime(PROJECT, METADATA, [member])
        member["Mounts"] = [{"Source": "/run/user/1000/podman/podman.sock", "Destination": "/engine"}]
        with self.assertRaises(ValueError):
            validate_runtime(PROJECT, METADATA, [member])

    def test_plan_cannot_override_isolation_before_startup(self):
        plan = {
            "networks": {"default": {"external": True, "name": NETWORK}},
            "services": {"runner": {"networks": {"default": {}}}},
        }
        validate_plan(plan, PROJECT)
        for value in (
            {},
            {"name": NETWORK},
            {"external": True, "name": "other"},
            {"external": False, "name": NETWORK},
        ):
            with self.subTest(network=value), self.assertRaises(ValueError):
                validate_plan(plan | {"networks": {"default": value}}, PROJECT)
        for service in (
            {"ports": ["8080:80"]},
            {"network_mode": "host"},
            {"privileged": True},
            {"networks": {"default": {}, "outside": {}}},
        ):
            with self.subTest(service=service), self.assertRaises(ValueError):
                validate_plan(plan | {"services": {"runner": service}}, PROJECT)
