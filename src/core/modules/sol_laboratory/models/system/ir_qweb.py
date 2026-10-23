from odoo import models


# Mẫu QWeb
class IrQweb(models.AbstractModel):
    _inherit = "ir.qweb"

    def _compile_directives(self, el, compile_context, level):
        # Mail views store this on the element. Left in place, qweb logs it as an unknown directive.
        el.attrib.pop("technical_usage", None)
        return super()._compile_directives(el, compile_context, level)
