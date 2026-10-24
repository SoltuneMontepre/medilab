from odoo.exceptions import UserError


class LaboratoryFileError(UserError):
    """A refusal of laboratory files, with the code the laboratory files API answers with and, for a refusal that
    passes, the seconds to wait before trying again."""

    def __init__(self, code, message, retry_after=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after
