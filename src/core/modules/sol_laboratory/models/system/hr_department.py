from odoo import models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
)

HR_VERSION = "hr.version"


# Phòng Ban
class HrDepartment(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_DEPARTMENT
    _inherit = [MODEL_DEPARTMENT, MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]

    def _search_has_read_access(self, operator, value):
        # Odoo's Departments menu lists only the departments they manage to people who cannot read employees.
        if operator == "in" and self._has_permission("read"):
            return Domain.TRUE
        return super()._search_has_read_access(operator, value)

    def _referring_fields(self):
        # People name their department through their employee's version; the person stands for it.
        fields = [field for field in super()._referring_fields() if field.model_name != HR_VERSION]
        return [*fields, self.env[MODEL_PERSON]._fields["department_id"]]
