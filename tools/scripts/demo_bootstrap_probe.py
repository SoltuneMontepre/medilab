"""Check the private HTTP registry and the report asset bundles from inside the Compose network."""

import argparse
import json
import os
import re
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

from odoo import SUPERUSER_ID, api
from odoo.modules.registry import Registry
from odoo.tools import config

ASSET_URL = re.compile(r"url\(\s*['\"]?([^)'\"]+)")
BASE_URL = "http://odoo:8069"
OPTIONAL_UPSTREAM_MISSING_ASSETS = frozenset(
    {
        "/base/static/src/img/layout/play-button.png",
        "/base/static/src/img/layout/play-button-over.png",
    }
)


def fetch(url):
    try:
        with urlopen(url, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"Asset request {url} returned HTTP {response.status}"
                )
            data = response.read()
            if not data:
                raise RuntimeError(f"Asset request {url} returned an empty body")
            return data
    except HTTPError as error:
        raise RuntimeError(f"Asset request {url} returned HTTP {error.code}") from error


def _wait_for_registry(database):
    readiness_url = f"{BASE_URL}/web/login?db={database}"
    last_error = "no response"
    for _attempt in range(120):
        try:
            with urlopen(readiness_url, timeout=2) as response:
                if response.status == 200:
                    break
                last_error = f"HTTP {response.status}"
        except OSError as error:
            last_error = type(error).__name__
        time.sleep(1)
    else:
        raise RuntimeError(
            f"Odoo registry did not become ready at {readiness_url}: {last_error}"
        )


def _report_asset_paths(database):
    registry = Registry(database)
    with registry.cursor() as cursor:
        env = api.Environment(cursor, SUPERUSER_ID, {"lang": "en_US"})
        installed = set(
            env["ir.module.module"].search([("state", "=", "installed")]).mapped("name")
        )
        if not {"sol_laboratory", "sol_commerce", "sol_demo"}.issubset(installed):
            raise RuntimeError(
                "The required MediLab modules are not installed in the private database"
            )
        nodes = env["ir.qweb"]._get_asset_nodes(
            "web.report_assets_common", css=True, js=True, autoprefix=True
        )
        paths = [
            attributes.get("href") or attributes.get("src")
            for _tag, attributes in nodes
        ]
        paths = [path for path in paths if path]
        if not paths:
            raise RuntimeError("Odoo returned no report asset URLs")
        cursor.commit()

    return paths


def _optional_font_fallback(url):
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "fonts.odoocdn.com"
        and parsed.path.startswith("/fonts/noto/NotoSans")
        and parsed.path.endswith((".woff2", ".woff", ".ttf"))
    )


def _css_asset(reference):
    reference = reference.strip()
    if reference.startswith(("data:", "#")):
        return None
    url = urljoin(BASE_URL, reference)
    if urlsplit(url).path in OPTIONAL_UPSTREAM_MISSING_ASSETS:
        # Odoo's module-description CSS references absent play-button images, unused by report templates.
        return "optional_missing_assets", url
    if urlsplit(url).netloc == urlsplit(BASE_URL).netloc:
        return "dependencies", url
    if _optional_font_fallback(url):
        return "optional_font_fallbacks", url
    raise RuntimeError(f"Report CSS references an external asset: {url}")


def _css_dependencies(css):
    assets = {
        "dependencies": set(),
        "optional_font_fallbacks": set(),
        "optional_missing_assets": set(),
    }
    for text in css:
        for reference in ASSET_URL.findall(text):
            asset = _css_asset(reference)
            if asset is not None:
                kind, url = asset
                assets[kind].add(url)
    return assets


def main(database):
    config.parse_config(
        [
            "--config=/etc/odoo/odoo.conf",
            "--db_host=" + os.environ["HOST"],
            "--db_user=" + os.environ["USER"],
            "--db_password=" + os.environ["PASSWORD"],
            "-d",
            database,
        ],
        setup_logging=True,
    )
    _wait_for_registry(database)
    paths = _report_asset_paths(database)
    origin = urlsplit(BASE_URL).netloc
    fetched = {}
    for path in paths:
        url = urljoin(BASE_URL, path)
        if urlsplit(url).netloc != origin:
            raise RuntimeError(
                f"Report asset points outside the private Odoo service: {url}"
            )
        fetched[url] = fetch(url)
    css = [
        data.decode("utf-8", errors="replace")
        for url, data in fetched.items()
        if urlsplit(url).path.endswith(".css")
    ]
    css_assets = _css_dependencies(css)
    dependencies = css_assets["dependencies"]
    optional_font_fallbacks = css_assets["optional_font_fallbacks"]
    optional_missing_assets = css_assets["optional_missing_assets"]
    for url in sorted(dependencies):
        fetched[url] = fetch(url)
    print(
        json.dumps(
            {
                "assets": len(paths),
                "css_dependencies": len(dependencies),
                "http": "ready",
                "optional_font_fallbacks": len(optional_font_fallbacks),
                "optional_missing_assets": len(optional_missing_assets),
            }
        )
    )


parser = argparse.ArgumentParser()
parser.add_argument("--database", required=True)
main(parser.parse_args().database)
