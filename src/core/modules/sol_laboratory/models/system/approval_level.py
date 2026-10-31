from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_CHAIN,
    MODEL_APPROVAL_LEVEL,
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_ROLE,
    MODEL_SIGNATURE,
    MODEL_SIGNING_PROCESS,
)

# Fields that decide who signs a level; a level that documents sign at keeps them, so changing one replaces the level.
SIGNING_FIELDS = frozenset({"chain_id", "sequence", "role_id", "same_department", "can_reject"})


# Cấp Phê Duyệt
class ApprovalLevel(models.Model):
    _name = MODEL_APPROVAL_LEVEL
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Approval Level"
    _order = "chain_id, sequence"
    _permission_actions = ("read", "create", "edit", "delete")

    # The chain the level belongs to.
    chain_id = fields.Many2one(MODEL_APPROVAL_CHAIN, string="Chain", required=True, ondelete="cascade")
    # Position in the chain; lower levels sign first.
    sequence = fields.Integer(required=True)
    # Level name in each language, such as "Head of department".
    name = fields.Char(required=True, translate=True)
    # The role a person needs to sign at this level.
    role_id = fields.Many2one(MODEL_ROLE, string="Role", required=True, ondelete="restrict")
    # True when the signer must belong to the department that did the work.
    same_department = fields.Boolean()
    # True when the signer may reject instead of signing.
    can_reject = fields.Boolean(default=True)

    # False once the level was replaced or removed while documents sign at it; they keep signing at it.
    active = fields.Boolean(default=True)

    _active_sequence_unique = models.UniqueIndex(
        "(chain_id, sequence) WHERE active", "A chain cannot have two levels in the same position."
    )

    def write(self, vals):
        held = self._held() if SIGNING_FIELDS & set(vals) else self.browse()
        if held:
            held._replace(vals)
        rest = self - held
        return super(ApprovalLevel, rest).write(vals) if rest else True

    def unlink(self):
        # A level that documents sign at is archived instead, so they keep it and only the chain loses it.
        held = self._held()
        if held:
            held._check_permission("delete")
            super(ApprovalLevel, held.sudo()).write({"active": False})
        rest = self - held
        return super(ApprovalLevel, rest).unlink() if rest else True

    def _held(self):
        # Levels a signing process or a signature refers to.
        processes = self.env[MODEL_SIGNING_PROCESS].sudo().search([("level_ids", "in", self.ids)])
        signatures = self.env[MODEL_SIGNATURE].sudo().search([("level_id", "in", self.ids)])
        return self & (processes._levels() | signatures.level_id)

    def _replace(self, vals):
        """Archive each level and add a copy with the new values to its chain: documents whose signing has started keep
        the level they had, later ones sign at the copy."""
        self._check_permission("edit")
        langs = [code for code, _name in self.env["res.lang"].get_installed()]
        for level in self.sudo():
            super(ApprovalLevel, level).write({"active": False})
            # The copy takes the level's position, which the archived level must have left first.
            level.flush_recordset(["active"])
            replacement = level.copy({"name": level.name, **vals, "active": True})
            if "name" not in vals:
                replacement.update_field_translations(
                    "name", {lang: level.with_context(lang=lang).name for lang in langs}
                )
