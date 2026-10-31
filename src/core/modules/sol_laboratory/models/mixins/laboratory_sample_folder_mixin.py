from typing import TYPE_CHECKING

from odoo import api, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN, MODEL_SAMPLE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_sample_folder_mixin as LaboratorySampleFolderMixinBase
else:
    LaboratorySampleFolderMixinBase = object


# Thư Mục Của Mẫu: records of a sample's folder only for people who see the sample
class LaboratorySampleFolderMixin(models.AbstractModel, LaboratorySampleFolderMixinBase):
    _name = MODEL_LABORATORY_SAMPLE_FOLDER_MIXIN
    _description = "Laboratory Records of a Sample's Folder"
    # Path from the record to its folder's sample, such as folder_id.sample_id.
    _sample_field = "folder_id.sample_id"

    @api.model
    def _access_domain(self, operation):
        """Add to every access of the model that the record's folder belongs to no sample, or to a sample the user
        sees, whoever the user is, folder administrators included. An access domain is evaluated with full rights, so
        it cannot test the sample itself; the sample's own access domain for the user can."""
        domain = super()._access_domain(operation)
        if domain.is_false():
            return domain
        samples = self.env[MODEL_SAMPLE]._access_domain("read")
        return domain & (Domain(self._sample_field, "=", False) | Domain(self._sample_field, "any", samples))
