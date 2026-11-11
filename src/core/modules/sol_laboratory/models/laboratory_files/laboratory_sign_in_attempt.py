import datetime
import math
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.laboratory_api import (
    FIRST_SIGN_IN_DELAY,
    FREE_SIGN_IN_FAILURES,
    LONGEST_SIGN_IN_DELAY,
    SIGN_IN_FAILURE_WINDOW,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import TOO_MANY_ATTEMPTS
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_LABORATORY_SIGN_IN_ATTEMPT,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_sign_in_attempt as LaboratorySignInAttemptBase
else:
    LaboratorySignInAttemptBase = object


# Lượt Đăng Nhập Sai: the failed sign-ins of a login through the laboratory files API, which slow its next ones. Only
# full rights reach it; the account itself is never locked.
class LaboratorySignInAttempt(models.Model, LaboratorySignInAttemptBase):
    _name = MODEL_LABORATORY_SIGN_IN_ATTEMPT
    _description = "Laboratory Sign-in Attempt"
    _log_access = False

    if not TYPE_CHECKING:
        # The login the failed sign-ins were made with, as it was sent; it need not be anyone's.
        login = fields.Char(required=True, readonly=True)
        # Failed sign-ins of the login since its failures were last forgotten.
        failures = fields.Integer(required=True, readonly=True)
        # When the last failed sign-in was made, to the microsecond.
        failed_at = fields.Datetime(required=True, readonly=True)

    _login_unique = models.Constraint("UNIQUE(login)", "A login has one count of failed sign-ins.")

    @api.model
    def _check_delay(self, login):
        """Refuse a sign-in of the login before its delay has passed, without checking its password. The delay doubles
        with each failure after the free ones, from the first delay up to the longest, counted from the last failure."""
        self.env.cr.execute(
            SQL("SELECT failures, failed_at FROM %s WHERE login = %s", SQL.identifier(self._table), login)
        )
        row = self.env.cr.fetchone()
        now = _now()
        if not row or row[0] < FREE_SIGN_IN_FAILURES or now - row[1] >= SIGN_IN_FAILURE_WINDOW:
            return
        delay = min(FIRST_SIGN_IN_DELAY * 2 ** (row[0] - FREE_SIGN_IN_FAILURES), LONGEST_SIGN_IN_DELAY)
        left = (row[1] + datetime.timedelta(seconds=delay) - now).total_seconds()
        if left > 0:
            raise LaboratoryFileError(
                TOO_MANY_ATTEMPTS,
                self.env._("Too many failed sign-ins with this login; try again in %s seconds.", math.ceil(left)),
                math.ceil(left),
            )

    @api.model
    def _check_address_cooldown(self, address):
        """Refuse a sign-in from the address while Odoo's own login cooldown holds it, which Odoo counts per address in
        each worker and would refuse as a wrong password."""
        failures, previous = getattr(self.env.registry, "_login_failures", {}).get(address, (0, datetime.datetime.min))
        users = self.env[MODEL_RES_USERS]
        if not users._on_login_cooldown(failures, previous):
            return
        duration = self.env[MODEL_IR_CONFIG_PARAMETER].sudo().get_int("base.login_cooldown_duration") or 60
        left = math.ceil(
            max((previous + datetime.timedelta(seconds=duration) - datetime.datetime.now()).total_seconds(), 1)
        )
        raise LaboratoryFileError(
            TOO_MANY_ATTEMPTS,
            self.env._("Too many failed sign-ins from this address; try again in %s seconds.", left),
            left,
        )

    @api.model
    def _record_failure(self, login):
        """Count a failed sign-in of the login. Two failures of one login at once update one row: the second fails with
        a serialization error and Odoo runs its request again, so each is counted once."""
        now = _now()
        self.env.cr.execute(
            SQL(
                """
                INSERT INTO %(table)s (login, failures, failed_at) VALUES (%(login)s, 1, %(now)s)
                ON CONFLICT (login) DO UPDATE SET
                    failures = CASE WHEN %(table)s.failed_at <= %(forgotten)s THEN 1 ELSE %(table)s.failures + 1 END,
                    failed_at = EXCLUDED.failed_at
                """,
                table=SQL.identifier(self._table),
                login=login,
                now=now,
                forgotten=now - SIGN_IN_FAILURE_WINDOW,
            )
        )
        self.invalidate_model()

    @api.model
    def _clear(self, login):
        """A sign-in succeeded: the login's failures are forgotten."""
        self.env.cr.execute(SQL("DELETE FROM %s WHERE login = %s", SQL.identifier(self._table), login))
        self.invalidate_model()

    @api.autovacuum
    def _gc_forgotten_failures(self):
        self.env.cr.execute(
            SQL(
                "DELETE FROM %s WHERE failed_at <= %s",
                SQL.identifier(self._table),
                _now() - SIGN_IN_FAILURE_WINDOW,
            )
        )


def _now():
    # To the microsecond, which the ORM's own now() drops, so a delay of a second is a whole second.
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
