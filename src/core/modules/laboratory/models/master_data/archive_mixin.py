from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.laboratory.constants.models import MODEL_ARCHIVE_MIXIN

LISTED_REFERENCES = 10


# Refuses archiving or deleting a record that other records still refer to, listing them.
class ArchiveMixin(models.AbstractModel):
    _name = MODEL_ARCHIVE_MIXIN
    _description = "Archiving and Deleting Rules"

    def _has_field_access(self, field, operation):
        # The interface offers Archive whenever the active field is writable.
        if field.name == "active" and operation == "write" and not self.browse().has_access("write"):
            return False
        return super()._has_field_access(field, operation)

    def write(self, vals):
        if vals.get("active") is False:
            self.filtered("active")._check_unused(archiving=True)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_in_use(self):
        self._check_unused(archiving=False)

    def _check_unused(self, archiving):
        if not self:
            return
        lines = []
        for field in self._referring_fields():
            referrers = self._find_referrers(field, archiving)
            if referrers:
                names = [referrer.display_name for referrer in referrers[:LISTED_REFERENCES]]
                if len(referrers) > LISTED_REFERENCES:
                    names.append("…")
                lines.append(f"{self.env['ir.model']._get(referrers._name).name}: {', '.join(names)}")
        if not lines:
            return
        if archiving:
            raise UserError(self.env._("This cannot be archived while these records use it:\n%s", "\n".join(lines)))
        raise UserError(self.env._("This cannot be deleted while these records refer to it:\n%s", "\n".join(lines)))

    def _referring_fields(self):
        # Relations deleted along with the record (ondelete cascade) are parts of it and never block it.
        return [
            field
            for model in self.env.registry.values()
            if not model._abstract and not model._transient
            for field in model._fields.values()
            if field.type in ("many2one", "many2many")
            and field.store
            and field.comodel_name == self._name
            and field.ondelete != "cascade"
        ]

    def _find_referrers(self, field, archiving):
        referrers = self.env[field.model_name].with_context(active_test=False)
        domain = Domain(field.name, "in", self.ids)
        if field.model_name == self._name:
            domain &= Domain("id", "not in", self.ids)
        if archiving:
            domain &= self._referrers_in_use(referrers)
        return referrers.search(domain, limit=LISTED_REFERENCES + 1)

    def _referrers_in_use(self, referrers):
        # A referring model states when its records are in use with _in_use_domain(); otherwise an active record is,
        # and a record of a model that states nothing always is, so archiving is never let through by mistake.
        if hasattr(referrers, "_in_use_domain"):
            return referrers._in_use_domain()
        if "active" in referrers._fields:
            return Domain("active", "=", True)
        return Domain.TRUE
