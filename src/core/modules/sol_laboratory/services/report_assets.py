"""Report HTML that wkhtmltopdf can print without a web server.

During --stop-after-init the HTTP port is closed. Styles and scripts are written into the HTML, and the
files they point at are embedded, so the PDF engine does not open a connection.
"""

import base64
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from lxml import etree, html
from markupsafe import Markup

from odoo.tools import config
from odoo.tools.misc import file_path

_URL = re.compile(r"""url\(\s*(?P<target>"[^"]*"|'[^']*'|[^()\s'"]+)\s*\)""")


def inline_report_assets(env, document):
    """The same HTML with its styles and scripts included, while Odoo is installing and not listening."""
    if not config.get("stop_after_init") or not document:
        return document
    binary = isinstance(document, bytes)
    root = html.fromstring(document.decode() if binary else str(document))
    for node in _elements(root, "link", "href"):
        _replace_link(env, node)
    for node in _elements(root, "script", "src"):
        _replace_script(env, node)
    for node in _elements(root, "base"):
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
    rendered = html.tostring(root, doctype="<!DOCTYPE html>", encoding="unicode")
    if binary:
        return rendered.encode()
    if isinstance(document, Markup):
        return Markup(rendered)
    return rendered


def _elements(root, tag, attribute=None):
    # Taken as a list first, because these nodes are replaced while the tree is walked.
    found = []
    for node in root.iter(tag):
        if attribute is None or node.get(attribute) is not None:
            found.append(node)
    return found


def _replace_link(env, node):
    href = node.get("href")
    parent = node.getparent()
    if parent is None or not href:
        return
    path = urlsplit(href).path
    if not _is_local(href):
        return
    if "stylesheet" in (node.get("rel") or "") or path.endswith(".css"):
        text = _bundle_text(env, href, kind="css")
        if text is None:
            parent.remove(node)
            return
        style = etree.Element("style")
        style.text = _keep_open(text)
        parent.replace(node, style)
        return
    parent.remove(node)


def _replace_script(env, node):
    parent = node.getparent()
    if parent is None:
        return
    text = _bundle_text(env, node.get("src"), kind="js")
    if text is None:
        parent.remove(node)
        return
    script = etree.Element("script")
    script.text = _keep_open(text)
    parent.replace(node, script)


def _bundle_text(env, url, kind):
    path = unquote(urlsplit(url).path)
    marker = "/web/assets/"
    if marker not in path:
        return None
    unique, _, filename = path.split(marker, 1)[1].partition("/")
    if not filename or "/" in filename:
        return None
    bundle_name, rtl, asset_type, autoprefix = env["ir.asset"]._parse_bundle_name(filename, unique == "debug")
    if asset_type != kind:
        return None
    bundle = env["ir.qweb"]._get_asset_bundle(
        bundle_name,
        css=kind == "css",
        js=kind == "js",
        debug_assets=unique == "debug",
        rtl=rtl,
        autoprefix=autoprefix,
    )
    attachment = bundle.css() if kind == "css" else bundle.js()
    raw = attachment[:1].raw
    if not raw:
        return None
    text = bytes(raw).decode()
    if kind == "css":
        text = _URL.sub(lambda match: _embed_url(env, match), text)
    return text


def _embed_url(env, match):
    target = match.group("target").strip()
    if target[0] in ("'", '"'):
        target = target[1:-1]
    if target.startswith("data:"):
        return match.group(0)
    payload = _static_bytes(env, target)
    if payload is None:
        # Anything still pointing at this machine would be refused. An address on another host stays.
        parsed = urlsplit(target)
        if parsed.scheme in ("http", "https") and parsed.hostname not in ("localhost", "127.0.0.1"):
            return match.group(0)
        return "url('data:,')"
    mime = mimetypes.guess_type(_parsed_path(target))[0] or "application/octet-stream"
    return f"url('data:{mime};base64,{base64.b64encode(payload).decode()}')"


def _keep_open(text):
    # A literal end tag in the file would close the element we just opened.
    return text.replace("</", "<\\/")


def _parsed_path(url):
    return urlsplit(url).path


def _static_bytes(env, url):
    path = unquote(_parsed_path(url) or url)
    if not path.startswith("/"):
        return None
    relative = path.lstrip("/")
    if relative and not relative.startswith("web/assets/"):
        try:
            return Path(file_path(relative)).read_bytes()
        except (FileNotFoundError, ValueError):
            return _attachment_bytes(env, path)
    return _attachment_bytes(env, path)


def _attachment_bytes(env, path):
    found = env["ir.attachment"].sudo().search([("url", "=", path)], limit=1)
    if not found or not found.raw:
        return None
    return bytes(found.raw)


def _is_local(url):
    parsed = urlsplit(url)
    if parsed.scheme in ("http", "https"):
        return parsed.hostname in ("localhost", "127.0.0.1")
    return url.startswith("/")
