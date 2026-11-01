from typing import TYPE_CHECKING

from odoo import api, models
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_GROUPS, MODEL_RES_USERS

if TYPE_CHECKING:
    from medilab_model_types import Model_res_groups as ResGroupsBase
else:
    ResGroupsBase = object


# Nhóm Quyền: adding a portal user to a group of internal users makes it internal, which only a person does.
class ResGroups(models.Model, ResGroupsBase):
    _inherit = MODEL_RES_GROUPS

    @api.model_create_multi
    def create(self, vals_list):
        commands = [command for vals in vals_list for command in vals.get("user_ids") or []]
        shared = self._added_users(commands).filtered("share")
        groups = super().create(vals_list)
        shared._check_internal_through_person()
        return groups

    def write(self, vals):
        shared = self._added_users(vals.get("user_ids") or []).filtered("share")
        if "implied_ids" in vals:
            # Odoo's check of user types skips archived users, though their type follows the groups too.
            shared |= self.with_context(active_test=False).all_implied_by_ids.user_ids.filtered("share")
        result = super().write(vals)
        shared._check_internal_through_person()
        return result

    def _added_users(self, commands):
        ids = set()
        for command in commands:
            if isinstance(command, int):
                ids.add(command)
            elif command[0] == Command.LINK:
                ids.add(command[1])
            elif command[0] == Command.SET:
                ids.update(command[2])
        return self.env[MODEL_RES_USERS].browse(ids)
