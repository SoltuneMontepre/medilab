from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER


# Thư Mục Phòng Thí Nghiệm: a sample has one folder of each category.
class LaboratoryFolderSample(models.Model):
    _inherit = MODEL_LABORATORY_FOLDER

    _sample_category_unique = models.Constraint(
        "UNIQUE(sample_id, category)", "The sample already has a folder of this category."
    )
    _sample_has_category = models.Constraint(
        "CHECK(sample_id IS NULL OR category IS NOT NULL)", "A folder of a sample needs a category."
    )

    def write(self, vals):
        # Once a folder holds files, they keep meaning its sample and category, such as a signed result of the sample.
        if self.sudo().filtered("file_ids")._changes_sample(vals):
            raise UserError(self.env._("A folder that holds files keeps its sample and its category."))
        return super().write(vals)

    def _changes_sample(self, vals):
        return any(
            ("sample_id" in vals and folder.sample_id.id != (vals["sample_id"] or False))
            or ("category" in vals and folder.category != (vals["category"] or False))
            for folder in self
        )
