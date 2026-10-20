from odoo.exceptions import UserError


class LaboratoryFileError(UserError):
    """A refusal of laboratory files, with the code the laboratory files API answers with."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
