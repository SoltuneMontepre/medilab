from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_SYNC_RULE,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
)
from odoo.addons.sol_laboratory.services.laboratory_paths import (
    is_extension,
    is_name_pattern,
    is_name_prefix,
    normal_extension,
    normal_text,
)

PATTERN_CHECKS = {"prefix": is_name_prefix, "glob": is_name_pattern, "extension": is_extension}


# Quy Tắc Đồng Bộ
class LaboratorySyncRule(models.Model):
    _name = MODEL_LABORATORY_SYNC_RULE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Laboratory Sync Rule"
    _order = "folder_id, id"
    _rec_name = "pattern"
    # A rule that is no longer wanted is removed or turned off.
    _permission_actions = ("read", "create", "edit", "delete")

    # The folder the rule limits.
    folder_id = fields.Many2one(MODEL_LABORATORY_FOLDER, string="Folder", required=True, ondelete="cascade", index=True)
    # prefix, glob or extension.
    kind = fields.Selection(
        [("prefix", "Name Prefix"), ("glob", "Name Pattern"), ("extension", "Extension")],
        required=True,
        default="prefix",
    )
    # The name prefix, pattern with * or extension the file must match; an extension without its dot, in lowercase.
    pattern = fields.Char(required=True)
    # True when files in subfolders count too.
    recursive = fields.Boolean(string="Include Subfolders", default=True)
    # False when the rule is turned off.
    enabled = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        self.env[MODEL_LABORATORY_FOLDER].browse(
            {vals["folder_id"] for vals in vals_list if vals.get("folder_id")}
        )._check_not_archived()
        for vals in vals_list:
            if vals.get("pattern"):
                vals["pattern"] = normal_text(vals["pattern"])
            if vals.get("kind", "prefix") == "extension" and vals.get("pattern"):
                vals["pattern"] = normal_extension(vals["pattern"])
        return super().create(vals_list)

    def write(self, vals):
        (self.folder_id | self.folder_id.browse(vals.get("folder_id") or []))._check_not_archived()
        if vals.get("pattern"):
            vals = {**vals, "pattern": normal_text(vals["pattern"])}
        if "pattern" not in vals and vals.get("kind") != "extension":
            return super().write(vals)
        # Each rule keeps its own pattern when only its kind changes, so an extension is made normal rule by rule.
        for rule in self:
            rule_vals = dict(vals)
            if vals.get("kind", rule.kind) == "extension":
                rule_vals["pattern"] = normal_extension(vals.get("pattern", rule.pattern) or "")
            super(LaboratorySyncRule, rule).write(rule_vals)
        return True

    @api.constrains("kind", "pattern")
    def _check_pattern(self):
        for rule in self:
            pattern = rule.pattern or ""
            if PATTERN_CHECKS[rule.kind](pattern):
                continue
            if rule.kind == "prefix":
                message = self.env._(
                    "A name prefix is the start of a file name, such as run-, without * or a path: %s", pattern
                )
            elif rule.kind == "glob":
                message = self.env._(
                    "A name pattern is a file name with *, such as run-*.csv, without a path: %s", pattern
                )
            else:
                message = self.env._("An extension is letters and digits, such as csv: %s", pattern)
            raise ValidationError(message)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_archived_folder(self):
        self.folder_id._check_not_archived()
