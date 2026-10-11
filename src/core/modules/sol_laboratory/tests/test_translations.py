import os
import tempfile
from collections import defaultdict

import polib

from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged
from odoo.tools.translate import TranslationModuleReader

from odoo.addons.sol_laboratory.constants.models import MODEL_ROLE

MODULE_PREFIX = "sol_"
VIETNAMESE_PO = os.path.join("i18n", "vi.po")


def untranslated_terms(env, po_paths):
    """Per module, the user-facing strings that its Vietnamese file at po_paths[module] does not translate."""
    # A role's group is named after the role's code, which is data, not a string of the module.
    role_groups = set(env[MODEL_ROLE].with_context(active_test=False).search([]).group_id.get_external_id().values())
    terms = defaultdict(set)
    for module, _type, _name, xml_id, source, _value, _comments in TranslationModuleReader(env.cr, list(po_paths)):
        if xml_id not in role_groups:
            terms[module].add(source)
    missing = {}
    for module, po_path in po_paths.items():
        translated = set()
        if os.path.isfile(po_path):
            translated = {entry.msgid for entry in polib.pofile(po_path).translated_entries()}
        if untranslated := sorted(terms[module] - translated):
            missing[module] = untranslated
    return missing


@tagged("post_install", "-at_install")
class TestTranslations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        modules = cls.env["ir.module.module"].search(
            [("name", "=like", f"{MODULE_PREFIX}%"), ("state", "=", "installed")]
        )
        cls.po_paths = {name: os.path.join(get_module_path(name), VIETNAMESE_PO) for name in modules.mapped("name")}

    def test_every_module_translates_its_strings_to_vietnamese(self):
        missing = untranslated_terms(self.env, self.po_paths)

        report = "\n".join(f"{module}: {term!r}" for module, terms in missing.items() for term in terms)
        self.assertFalse(missing, f"Strings missing from i18n/vi.po:\n{report}")

    def test_a_string_missing_from_vi_po_is_reported(self):
        po = polib.pofile(self.po_paths["sol_laboratory"])
        removed = po.translated_entries()[0]
        po.remove(removed)

        with tempfile.TemporaryDirectory() as folder:
            po_path = os.path.join(folder, "vi.po")
            po.save(po_path)
            missing = untranslated_terms(self.env, {"sol_laboratory": po_path})

        self.assertIn(removed.msgid, missing["sol_laboratory"])
