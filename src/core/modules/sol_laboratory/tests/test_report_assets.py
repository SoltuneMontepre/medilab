import base64
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from lxml import html
from markupsafe import Markup

from odoo.tests import TransactionCase, tagged
from odoo.tools import config

from odoo.addons.base.models.assetsbundle import AssetsBundle
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REPORT_REPORT
from odoo.addons.sol_laboratory.services.report_assets import inline_report_assets

CSS_URL = "/web/assets/123/web.report_assets_common.min.css"
JS_URL = "/web/assets/123/web.report_assets_pdf.min.js"
IMAGE = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'


@tagged("post_install", "-at_install")
class TestReportAssets(TransactionCase):
    def setUp(self):
        super().setUp()
        options = patch.dict(config.options, {"stop_after_init": True})
        options.start()
        self.addCleanup(options.stop)

    def attachment(self, content, mimetype, url=None):
        return self.env["ir.attachment"].create(
            {"name": "report asset", "raw": content, "mimetype": mimetype, "url": url}
        )

    def inline(self, document, css=b"body { color: red; }", js=b"window.reportReady = true;"):
        styles = self.attachment(css, "text/css") if css else self.env["ir.attachment"]
        scripts = self.attachment(js, "text/javascript") if js else self.env["ir.attachment"]
        # The compiler returns real attachments; URL resolution, parsing and embedding run unchanged.
        with (
            patch.object(AssetsBundle, "css", return_value=styles),
            patch.object(AssetsBundle, "js", return_value=scripts),
        ):
            return inline_report_assets(self.env, document)

    def page(self, head):
        return f"<html><head>{head}</head><body><p>Laboratory report</p></body></html>"

    def test_running_reports_keep_their_original_assets(self):
        page = self.page(f'<link rel="stylesheet" href="{CSS_URL}"/>')
        with patch.dict(config.options, {"stop_after_init": False}):
            self.assertEqual(inline_report_assets(self.env, page), page)

    def test_absent_headers_and_footers_stay_absent(self):
        for document in (None, "", b""):
            with self.subTest(document=document):
                self.assertEqual(inline_report_assets(self.env, document), document)

    def test_styles_and_scripts_are_embedded_and_base_addresses_are_removed(self):
        document = self.page(
            f'<base href="http://localhost:8069"/><link rel="stylesheet" href="{CSS_URL}"/>'
            f'<script src="{JS_URL}"></script>'
        )

        root = html.fromstring(self.inline(document))

        self.assertFalse(root.xpath("//base | //link | //script[@src]"))
        self.assertEqual(root.xpath("//style/text()"), ["body { color: red; }"])
        self.assertEqual(root.xpath("//script/text()"), ["window.reportReady = true;"])
        self.assertIn("Laboratory report", root.text_content())

    def test_embedding_preserves_bytes_and_safe_markup(self):
        page = self.page(f'<link href="{CSS_URL}"/>')
        for document in (page.encode(), Markup(page)):
            with self.subTest(kind=type(document)):
                rendered = self.inline(document)
                self.assertIsInstance(rendered, type(document))
                self.assertIn("color: red", rendered.decode() if isinstance(rendered, bytes) else rendered)

    def test_external_stylesheets_are_preserved(self):
        root = html.fromstring(self.inline(self.page('<link rel="stylesheet" href="https://cdn.example/report.css"/>')))

        self.assertEqual(root.xpath("//link/@href"), ["https://cdn.example/report.css"])

    def test_local_icons_and_unavailable_bundles_are_removed(self):
        page = self.page(
            '<link rel="icon" href="/missing.ico"/><link rel="stylesheet" href="/missing.css"/>'
            '<script src="/missing.js"></script><link rel="stylesheet"/>'
        )
        root = html.fromstring(self.inline(page))

        self.assertFalse(root.xpath("//link[@href] | //script[@src]"))
        self.assertEqual(len(root.xpath("//link[not(@href)]")), 1)

    def test_an_empty_bundle_is_removed(self):
        root = html.fromstring(
            self.inline(self.page(f'<link href="{CSS_URL}"/><script src="{JS_URL}"></script>'), css=b"", js=b"")
        )

        self.assertFalse(root.xpath("//link | //script | //style"))

    def test_invalid_bundle_paths_and_wrong_asset_types_are_removed(self):
        for path in ("/web/assets/123/", "/web/assets/123/nested/file.css", JS_URL):
            with self.subTest(path=path):
                root = html.fromstring(self.inline(self.page(f'<link rel="stylesheet" href="{path}"/>')))
                self.assertFalse(root.xpath("//link | //style"))

    def test_debug_assets_are_embedded(self):
        root = html.fromstring(self.inline(self.page('<link href="/web/assets/debug/web.report_assets_common.css"/>')))

        self.assertEqual(root.xpath("//style/text()"), ["body { color: red; }"])

    def test_absolute_local_asset_addresses_are_embedded(self):
        for host in ("localhost", "127.0.0.1"):
            with self.subTest(host=host):
                root = html.fromstring(self.inline(self.page(f'<link href="http://{host}:8069{CSS_URL}"/>')))
                self.assertEqual(root.xpath("//style/text()"), ["body { color: red; }"])

    def test_attached_images_are_embedded_with_their_mime_type(self):
        self.attachment(IMAGE, "image/svg+xml", "/web/assets/report-picture.svg")
        expected = "data:image/svg+xml;base64," + base64.b64encode(IMAGE).decode()
        for target in (
            "/web/assets/report-picture.svg",
            "http://localhost:8069/web/assets/report-picture.svg?version=1",
        ):
            for quote in ("", "'", '"'):
                with self.subTest(target=target, quote=quote):
                    css = f"body {{ background: url( {quote}{target}{quote} ); }}".encode()
                    root = html.fromstring(self.inline(self.page(f'<link href="{CSS_URL}"/>'), css=css))
                    self.assertIn(expected, root.findtext(".//style", default=""))

    def test_report_images_are_embedded_from_local_image_routes(self):
        attachment = self.attachment(IMAGE, "image/svg+xml")
        expected = "data:image/svg+xml;base64," + base64.b64encode(IMAGE).decode()
        for route in (f"ir.attachment/{attachment.id}/raw", str(attachment.id)):
            with self.subTest(route=route):
                image = f"http://localhost:8069/web/image/{route}"
                root = html.fromstring(self.inline(self.page(f'<img src="{image}"/>')))

                self.assertEqual(root.xpath("//img/@src"), [expected])

    def test_unavailable_local_report_images_are_removed(self):
        root = html.fromstring(self.inline(self.page('<img src="http://localhost:8069/web/image/ir.attachment/0/raw"/>')))

        self.assertFalse(root.xpath("//img[@src]"))

    def test_a_quoted_image_address_can_contain_parentheses(self):
        self.attachment(IMAGE, "image/svg+xml", "/web/assets/report(copy).svg")
        css = b"body { background: url('/web/assets/report(copy).svg'); }"

        root = html.fromstring(self.inline(self.page(f'<link href="{CSS_URL}"/>'), css=css))

        self.assertIn("data:image/svg+xml;base64,", root.findtext(".//style", default=""))

    def test_static_addon_images_are_embedded(self):
        css = b"body { background: url('/sol_laboratory/static/src/img/test_report.svg'); }"

        root = html.fromstring(self.inline(self.page(f'<link href="{CSS_URL}"/>'), css=css))

        self.assertIn("data:image/svg+xml;base64,", root.findtext(".//style", default=""))

    def test_existing_data_and_external_image_addresses_are_preserved(self):
        for target in ("data:image/png;base64,YWJj", "https://cdn.example/report.svg"):
            with self.subTest(target=target):
                css = f"body {{ background: url('{target}'); }}".encode()
                root = html.fromstring(self.inline(self.page(f'<link href="{CSS_URL}"/>'), css=css))
                self.assertEqual(root.findtext(".//style", default=""), css.decode())

    def test_unavailable_local_images_never_open_a_connection(self):
        self.attachment(b"", "image/png", "/web/assets/empty.png")
        for target in ("missing.png", "/missing.png", "http://localhost/missing.png", "/web/assets/empty.png"):
            with self.subTest(target=target):
                css = f"body {{ background: url('{target}'); }}".encode()
                root = html.fromstring(self.inline(self.page(f'<link href="{CSS_URL}"/>'), css=css))
                self.assertEqual(root.xpath("//style/text()"), ["body { background: url('data:,'); }"])

    def test_unknown_image_types_are_embedded_as_binary(self):
        self.attachment(b"abc", "application/octet-stream", "/web/assets/report.unknown_extension")
        css = b"body { background: url('/web/assets/report.unknown_extension'); }"

        root = html.fromstring(self.inline(self.page(f'<link href="{CSS_URL}"/>'), css=css))

        self.assertIn("data:application/octet-stream;base64,YWJj", root.findtext(".//style", default=""))

    def test_an_asset_cannot_close_its_html_element(self):
        page = self.page(f'<link href="{CSS_URL}"/><script src="{JS_URL}"></script>')
        root = html.fromstring(self.inline(page, css=b'body:after { content: "</style>"; }', js=b'var x="</script>";'))

        self.assertEqual(root.xpath("//style/text()"), ['body:after { content: "<\\/style>"; }'])
        self.assertEqual(root.xpath("//script/text()"), ['var x="<\\/script>";'])

    def test_unterminated_css_urls_finish_without_backtracking_through_whitespace(self):
        source = Path(__file__).parents[1] / "services" / "report_assets.py"
        code = """
import runpy
import sys
pattern = runpy.run_path(sys.argv[1])["_URL"]
css = "url(" + " " * 5000 + '"'
if pattern.sub(lambda match: match.group(0), css) != css:
    raise AssertionError("An unterminated CSS URL was changed.")
"""
        subprocess.run([sys.executable, "-c", code, str(source)], check=True, timeout=5, capture_output=True)

    def test_odoo_prepares_printable_bodies_headers_and_footers_without_http_assets(self):
        report = self.env.ref(TEST_REPORT_REPORT)
        page = '<html><main><div class="header">Header</div><div class="article">Result</div>'
        page += '<div class="footer">Footer</div></main></html>'

        bodies, _ids, header, footer, _specific = report._prepare_html(page)

        for document in [*bodies, header, footer]:
            with self.subTest(document=document[:80]):
                root = html.fromstring(str(document))
                self.assertFalse(root.xpath("//base | //link[@href] | //script[@src]"))
                self.assertTrue(root.xpath("//style"))
