from typing import TYPE_CHECKING, Self

from psycopg2 import IntegrityError, errorcodes

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_IDEMPOTENCY_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_idempotency_mixin as LaboratoryIdempotencyMixinBase
else:
    LaboratoryIdempotencyMixinBase = object


# Yêu Cầu Một Lần: records a computer creates through the laboratory files API with a key of its own, so a request it
# repeats finds the record the first one created. A model that inherits it declares a unique index on its computer field
# and the key, where the key is set.
class LaboratoryIdempotencyMixin(models.AbstractModel, LaboratoryIdempotencyMixinBase):
    _name = MODEL_LABORATORY_IDEMPOTENCY_MIXIN
    _description = "Laboratory Record Created Once per Request"
    # The field of the computer that created the record; a key is unique for its computer.
    _idempotency_device_field = "device_id"

    if not TYPE_CHECKING:
        # The Idempotency-Key the computer sent with the request that created the record; empty when it sent none.
        idempotency_key = fields.Char(readonly=True, copy=False)

    @api.model
    def _created_with_key(self, device, key) -> Self:
        """The record the computer created with the key, or no record."""
        if not key:
            return self.browse()
        found = self.sudo().search(
            [(self._idempotency_device_field, "=", device.id), ("idempotency_key", "=", key)], limit=1
        )
        return found.with_env(self.env)

    @api.model
    def _create_once(self, device, key, values) -> Self:
        """Create the record of the computer's request with its key. Two requests at once that would make the same
        record, by the key or by another unique key of the model, make one: the second one's creation fails on the
        unique key and Odoo runs its request again, which then finds the record."""
        values = {**values, self._idempotency_device_field: device.id, "idempotency_key": key or False}
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                return self.create(values)
        except IntegrityError as error:
            if error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            # Committed by a transaction this one cannot see; ConcurrencyError is what Odoo's request retrying retries.
            raise ConcurrencyError(
                self.env._("Another request made the same record meanwhile; the request is run again.")
            ) from error
