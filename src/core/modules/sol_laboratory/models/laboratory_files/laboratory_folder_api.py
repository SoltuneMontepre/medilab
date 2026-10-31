from typing import TYPE_CHECKING

from psycopg2 import IntegrityError, errorcodes

from odoo import api, models
from odoo.exceptions import ConcurrencyError
from odoo.fields import Domain
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.laboratory_api import CANDIDATE_LIMIT, CANDIDATE_QUERY_MIN_LENGTH
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FOLDER_EXISTS,
    FOLDER_SHARE,
    IDEMPOTENCY_CONFLICT,
    INVALID_REQUEST,
    MEMBER_ROLE,
    NOT_FOUND,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_LABORATORY_IDEMPOTENCY_MIXIN,
    MODEL_LABORATORY_SYNC_RULE,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.laboratory_paths import normal_text

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_folder as LaboratoryFolderApiBase
else:
    LaboratoryFolderApiBase = object

# The logger of the queries a unique key refuses, which a save point catches and answers itself.
SQL_LOGGER = "odoo.sql_db"


# Thư Mục Phòng Thí Nghiệm: what the laboratory files API does with folders once it has checked access; a computer
# creates a folder once per Idempotency-Key.
class LaboratoryFolderApi(models.Model, LaboratoryFolderApiBase):
    _name = MODEL_LABORATORY_FOLDER
    _inherit = [MODEL_LABORATORY_FOLDER, MODEL_LABORATORY_IDEMPOTENCY_MIXIN]
    _idempotency_device_field = "created_by_device_id"

    _device_idempotency_key_unique = models.UniqueIndex(
        "(created_by_device_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
        "This computer already created a folder with this Idempotency-Key.",
    )

    @api.model
    def _checked_for(self, folder_id, access):
        """The folder of the id once the user may do the access with it; a folder they may not read is not found."""
        # Odoo browses the id 0 as no record, which no check would refuse.
        folder = self.browse(folder_id)
        if not folder:
            raise LaboratoryFileError(
                NOT_FOUND, self.env._("This laboratory folder does not exist or you do not have access to it.")
            )
        folder._check_folder_access(access)
        return folder

    def _file_of(self, file_id):
        """The file of the id in this folder, for the user; a file of another folder, or of no id, is not found."""
        self.ensure_one()
        file = self.sudo().file_ids.filtered(lambda row: row.id == file_id)
        if not file:
            raise LaboratoryFileError(NOT_FOUND, self.env._("This file does not exist in the folder."))
        return file.with_env(self.env)

    @api.model
    def _create_for_device(self, device, name, key=None):
        """The folder of the name the person creates from the computer, owned by them. A request repeated with its
        Idempotency-Key gets the folder it created; otherwise a name the person already has a folder of is refused."""
        root = normal_text(name)
        created = self._created_with_key(device, key)
        if created:
            if created.root != root:
                raise LaboratoryFileError(
                    IDEMPOTENCY_CONFLICT, self.env._("This Idempotency-Key was already sent with another request.")
                )
            return created
        if self.sudo().search_count([("owner_id", "=", self.env.uid), ("root", "=", root)]):
            raise LaboratoryFileError(FOLDER_EXISTS, self.env._("You already have a folder named %s.", root))
        return self._create_once(device, key, {"name": name})

    def _laboratory_api_values(self):
        """The folder as the laboratory files API gives it to the user."""
        self.ensure_one()
        folder = self.sudo()
        member = folder.member_ids.filtered(lambda row: row.user_id == self.env.user)
        return {
            "id": folder.id,
            "name": folder.name,
            "root": folder.root,
            "sync_mode": folder.sync_mode,
            "status": folder.status,
            "role": member.role or None,
            "category": folder.category or None,
            "sample": {"id": folder.sample_id.id, "lab_code": folder.sample_id.code} if folder.sample_id else None,
            "retention_until": folder.retention_until.isoformat() if folder.retention_until else None,
            "can_share": self._can_share(),
        }

    def _can_share(self):
        try:
            self._check_folder_access(FOLDER_SHARE)
        except LaboratoryFileError:
            return False
        return True

    def _add_member(self, user_id):
        """The member row of the person, added when they are not a member yet, so adding them again finds it. Two
        additions at once make one row: the second one fails on the unique member and Odoo runs its request again."""
        self.ensure_one()
        members = self.env[MODEL_LABORATORY_FOLDER_MEMBER].sudo()
        member = members.search([("folder_id", "=", self.id), ("user_id", "=", user_id)])
        if member:
            return member
        members._check_eligible({user_id})
        try:
            with self.env.cr.savepoint(), mute_logger(SQL_LOGGER):
                return members.create({"folder_id": self.id, "user_id": user_id, "role": MEMBER_ROLE})
        except IntegrityError as error:
            if error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            raise ConcurrencyError(
                self.env._("Another request added this member meanwhile; the request is run again.")
            ) from error

    def _add_rule(self, kind, pattern, recursive):
        """The sync rule of the kind and pattern, added when the folder has none, so adding it again finds it; a rule
        found keeps its own flags, which a change of the rule sets. Two additions at once make one rule."""
        self.ensure_one()
        rules = self.env[MODEL_LABORATORY_SYNC_RULE].sudo()
        pattern = rules._normal_pattern(kind, pattern)
        rule = rules.search([("folder_id", "=", self.id), ("kind", "=", kind), ("pattern", "=", pattern)])
        if rule:
            return rule
        try:
            with self.env.cr.savepoint(), mute_logger(SQL_LOGGER):
                return rules.create({"folder_id": self.id, "kind": kind, "pattern": pattern, "recursive": recursive})
        except IntegrityError as error:
            if error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            raise ConcurrencyError(
                self.env._("Another request added this sync rule meanwhile; the request is run again.")
            ) from error

    def _change_rule(self, rule_id, values):
        """Change a sync rule of the folder. A rule changed into one of the kind and pattern of another is refused."""
        self.ensure_one()
        rule = self.sudo().rule_ids.filtered(lambda row: row.id == rule_id)
        if not rule:
            raise LaboratoryFileError(NOT_FOUND, self.env._("This sync rule does not exist in the folder."))
        try:
            with self.env.cr.savepoint(), mute_logger(SQL_LOGGER):
                rule.write(values)
                rule.flush_recordset()
        except IntegrityError as error:
            if error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            raise LaboratoryFileError(INVALID_REQUEST, self.env._("The folder already has this sync rule.")) from error
        return rule

    def _member_candidates(self, query):
        """The people the user can add to the folder whose name or login holds the query: eligible, and not members
        yet. The query has the shortest length searched, and the answer the most people one search finds."""
        self.ensure_one()
        query = (query or "").strip()
        if len(query) < CANDIDATE_QUERY_MIN_LENGTH:
            raise LaboratoryFileError(
                INVALID_REQUEST,
                self.env._("Type at least %s characters of the person's name or login.", CANDIDATE_QUERY_MIN_LENGTH),
            )
        domain = (
            self.env[MODEL_LABORATORY_FOLDER_MEMBER]._eligible_domain()
            & Domain("id", "not in", self.sudo().member_ids.user_id.ids)
            & (Domain("name", "ilike", query) | Domain("login", "ilike", query))
        )
        return self.env[MODEL_RES_USERS].sudo().search(domain, limit=CANDIDATE_LIMIT, order="name, id")
