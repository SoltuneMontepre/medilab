import os
import tempfile
from collections import defaultdict

import polib

from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path
from odoo.tools.translate import PoFileReader, TranslationModuleReader

from odoo.addons.sol_laboratory.constants.models import MODEL_ROLE
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

MODULE_PREFIX = "sol_"
LABORATORY = "sol_laboratory"
VIETNAMESE_PO = os.path.join("i18n", "vi.po")


def translated_terms(po_path):
    """The (string, place) pairs Odoo translates from the file at po_path.

    Odoo reads a module's vi.po merged with its .pot, whose references replace those of vi.po, and applies a record or
    view translation only to the references the entry lists. A code translation applies to the string wherever the
    code is, as long as the entry is marked as Python or JavaScript.
    """
    translated = set()
    if not os.path.isfile(po_path):
        return translated
    for row in PoFileReader(po_path):
        if not row["value"]:
            continue
        if row["type"] == "code":
            translated.update((row["src"], comment) for comment in row["comments"].split("\n"))
        else:
            translated.add((row["src"], f"{row['type']}:{row['name']}:{row['module']}.{row['imd_name']}"))
    return translated


def untranslated_terms(env, po_paths):
    """Per module, the user-facing (string, place) pairs its Vietnamese file at po_paths[module] leaves in English."""
    # A role's group is named after the role's code, which is data, not a string of the module.
    role_groups = set(env[MODEL_ROLE].with_context(active_test=False).search([]).group_id.get_external_id().values())
    terms = defaultdict(set)
    for module, kind, name, xml_id, source, _value, comments in TranslationModuleReader(env.cr, list(po_paths)):
        if kind == "code":
            terms[module].update((source, comment) for comment in comments)
        elif xml_id not in role_groups:
            terms[module].add((source, f"{kind}:{name}:{xml_id}"))
    missing = {}
    for module, po_path in po_paths.items():
        if untranslated := sorted(terms[module] - translated_terms(po_path)):
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
        cls.po_paths = {
            name: os.path.join(file_path(assert_instance(name, str)), VIETNAMESE_PO) for name in modules.mapped("name")
        }

    def _laboratory_template(self):
        return polib.pofile(os.path.join(os.path.dirname(self.po_paths[LABORATORY]), f"{LABORATORY}.pot"))

    def _missing_from(self, po, template):
        """What the laboratory module leaves in English when its Vietnamese file and template are the given ones."""
        with tempfile.TemporaryDirectory() as folder:
            i18n = os.path.join(folder, LABORATORY, "i18n")
            os.makedirs(i18n)
            template.save(os.path.join(i18n, f"{LABORATORY}.pot"))
            po.save(os.path.join(i18n, "vi.po"))
            return untranslated_terms(self.env, {LABORATORY: os.path.join(i18n, "vi.po")}).get(LABORATORY, [])

    def test_every_module_translates_its_strings_to_vietnamese(self):
        missing = untranslated_terms(self.env, self.po_paths)

        report = "\n".join(
            f"{module}: {source!r} at {place}" for module, terms in missing.items() for source, place in terms
        )
        self.assertFalse(missing, f"Strings left in English by i18n/vi.po merged with the template:\n{report}")

    def test_a_string_missing_from_vi_po_is_reported(self):
        po = polib.pofile(self.po_paths[LABORATORY])
        removed = po.translated_entries()[0]
        po.remove(removed)

        missing = self._missing_from(po, self._laboratory_template())

        self.assertIn(removed.msgid, {source for source, _place in missing})

    def test_a_reference_missing_from_the_template_is_reported(self):
        place = "model:ir.model,name:sol_laboratory.model_medilab_sample_type"
        template = self._laboratory_template()
        entry = assert_instance(template.find("Sample Type"), polib.POEntry)
        entry.occurrences = [(name, line) for name, line in entry.occurrences if name != place]

        missing = self._missing_from(polib.pofile(self.po_paths[LABORATORY]), template)

        self.assertIn(("Sample Type", place), missing)
