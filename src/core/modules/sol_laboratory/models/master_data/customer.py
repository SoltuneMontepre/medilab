import base64

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command, Domain
from odoo.tools import format_list
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.sol_laboratory.constants.customers import CUSTOMER_TYPE_BUSINESS
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_CONTACT_MIXIN,
    MODEL_CUSTOMER,
    MODEL_PERMISSION_MIXIN,
)
from odoo.addons.sol_laboratory.constants.xml_ids import CUSTOMER_EDITOR_GROUP

RES_PARTNER = "res.partner"
PARTNER_MERGE = "base.partner.merge.automatic.wizard"
LOGO_MIMETYPES = ("image/png", "image/jpeg")
LOGO_MAX_BYTES = 2 * 1024 * 1024
SIGNUP_KEYS = ("customer_type", "company_name", "phone", "street", "city", "vat", "citizen_id")
CONTACT_PERSON_KEYS = ("name", "function", "email", "phone")
# What the customer form changes on its people and addresses, which are written with full rights.
CHILD_KEYS = frozenset({"type", "name", "function", "email", "phone", "street", "city"})


# Khách Hàng
class Customer(models.Model):
    _name = MODEL_CUSTOMER
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN, MODEL_CONTACT_MIXIN]
    _inherits = {RES_PARTNER: "partner_id"}
    _description = "Customer"
    _order = "code"
    _rec_names_search = ("name", "code")
    # The customer's permissions govern its contact and people, not Odoo's contact rights, which only administrators hold.
    _check_inherits_access = False
    _contact_fields = (
        "name",
        "vat",
        "street",
        "street2",
        "city",
        "zip",
        "country_id",
        "phone",
        "email",
        "lang",
        "image_1920",
        "child_ids",
    )

    # Unique code of the customer, such as KH.0001; filled from a sequence when left empty.
    code = fields.Char(required=True, copy=False)
    # The contact holding the customer's details: name, address, email, phone, and for a company its people.
    partner_id = fields.Many2one(RES_PARTNER, required=True, ondelete="restrict")
    # Citizen ID of an individual: personal data, read only by those who maintain customers.
    citizen_id = fields.Char(string="Citizen ID", copy=False, groups=CUSTOMER_EDITOR_GROUP)
    # The person of a business the laboratory contacts by default; empty for an individual, who is their own contact.
    default_contact_id = fields.Many2one(
        RES_PARTNER,
        ondelete="set null",
        index="btree_not_null",
        domain="[('parent_id', '=', partner_id), ('type', '=', 'contact')]",
    )
    # The existing customer a self-registered account matched on tax code or citizen ID; empty when not flagged or once sales reviewed it.
    duplicate_of_id = fields.Many2one(
        MODEL_CUSTOMER, string="Possible Duplicate Of", ondelete="set null", index="btree_not_null", readonly=True
    )
    # Self-registered accounts flagged as possible duplicates of this customer.
    possible_duplicate_ids = fields.One2many(MODEL_CUSTOMER, "duplicate_of_id", string="Possible Duplicates")
    # False when the customer is archived.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a customer must be unique.")
    _partner_unique = models.Constraint("UNIQUE(partner_id)", "This contact is already a customer.")

    def _check_contact_values(self, contact):
        if contact.get("image_1920"):
            self._check_logo(contact["image_1920"])
        own = self.partner_id.child_ids.ids
        for command in contact.get("child_ids", ()):
            if command[0] != Command.CREATE and command[1] not in own:
                raise AccessError(self.env._("Only the customer's own people can be changed here."))
            if command[0] in (Command.CREATE, Command.UPDATE) and set(command[2]) - CHILD_KEYS:
                raise AccessError(
                    self.env._(
                        "Only the name, position, email, phone and address of the customer's people change here."
                    )
                )

    def _check_logo(self, image):
        data = base64.b64decode(image)
        if len(data) > LOGO_MAX_BYTES or guess_mimetype(data) not in LOGO_MIMETYPES:
            raise UserError(self.env._("The logo must be a PNG or JPEG image of at most 2 MB."))

    @api.model
    def _of_user(self, user):
        """The customer whose documents a portal user sees."""
        return self.sudo().search([("partner_id", "=", user.partner_id.commercial_partner_id.id)], limit=1)

    @api.model
    def _check_signup_details(self, details):
        business = details.get("customer_type") == CUSTOMER_TYPE_BUSINESS
        required = {
            "phone": self.env._("Phone"),
            "street": self.env._("Address"),
            "city": self.env._("City"),
            "vat": self.env._("Tax code"),
        }
        if business:
            required["company_name"] = self.env._("Company name")
        else:
            required["citizen_id"] = self.env._("Citizen ID")
        missing = [label for key, label in required.items() if not (details.get(key) or "").strip()]
        if missing:
            raise UserError(self.env._("Fill in: %s", format_list(self.env, missing)))

    @api.model
    def _create_from_signup(self, user, details):
        """Create the customer of a self-registered user, flagged when its identity matches an existing customer."""
        details = {key: (details.get(key) or "").strip() for key in SIGNUP_KEYS}
        match = self._identity_match(details["vat"], details["citizen_id"])
        address = {
            "phone": details["phone"],
            "street": details["street"],
            "city": details["city"],
            "country_id": self.env.company.country_id.id,
        }
        person = user.partner_id
        if details["customer_type"] == CUSTOMER_TYPE_BUSINESS:
            company = self.env[RES_PARTNER].create(
                {"name": details["company_name"], "vat": details["vat"], "email": user.email, **address}
            )
            person.write({"parent_id": company.id, "phone": details["phone"]})
            values = {"partner_id": company.id, "default_contact_id": person.id}
        else:
            person.write({"vat": details["vat"], **address})
            values = {"partner_id": person.id, "citizen_id": details["citizen_id"]}
        return self.create({**values, "duplicate_of_id": match.id})

    @api.model
    def _identity_match(self, vat, citizen_id):
        domain = Domain("partner_id.vat", "=", vat)
        if citizen_id:
            domain |= Domain("citizen_id", "=", citizen_id)
        return self.sudo().search(domain & Domain("duplicate_of_id", "=", False), order="id", limit=1)

    def action_clear_duplicate(self):
        """Sales reviewed the flag: the customer is not a duplicate."""
        self.write({"duplicate_of_id": False})
        return True

    def action_merge_duplicate(self):
        """Merge a flagged customer into the customer it matched, which keeps every document and person."""
        self.ensure_one()
        target = self.duplicate_of_id
        if not target:
            raise UserError(self.env._("This customer is not flagged as a possible duplicate."))
        (self | target).check_access("write")
        merge = self.env[PARTNER_MERGE].sudo()
        duplicate = self.sudo()
        partner = duplicate.partner_id
        merge._update_foreign_keys_generic(MODEL_CUSTOMER, duplicate, target)
        merge._update_reference_fields_generic(MODEL_CUSTOMER, duplicate, target)
        duplicate.unlink()
        merge._merge((partner | target.partner_id).ids, target.partner_id)
        # The merge moved the references in SQL, so nothing read before it is still true.
        self.env.invalidate_all()
        return {"type": "ir.actions.act_window", "res_model": MODEL_CUSTOMER, "res_id": target.id, "view_mode": "form"}

    def action_invite_to_portal(self):
        """Open Odoo's portal access wizard on the customer and its people."""
        self.ensure_one()
        self.check_access("write")
        return self.env["portal.wizard"].with_context(active_ids=self.partner_id.ids).action_open_wizard()

    def _contacts(self):
        self.ensure_one()
        return self.partner_id.child_ids.filtered(lambda partner: partner.type == "contact")

    def _check_own_contact(self, contact):
        self.ensure_one()
        if contact.parent_id != self.partner_id or contact.type != "contact":
            raise AccessError(self.env._("This person is not one of your contacts."))

    def save_contact(self, values, contact=None):
        """Add a person of the business, or change one."""
        self.ensure_one()
        values = {key: (values.get(key) or "").strip() for key in CONTACT_PERSON_KEYS}
        if not values["name"]:
            raise UserError(self.env._("Enter the contact's name."))
        if contact:
            self._check_own_contact(contact)
            contact.write(values)
            return contact
        return self.env[RES_PARTNER].create({**values, "parent_id": self.partner_id.id, "type": "contact"})

    def remove_contact(self, contact):
        """Archive a person of the business; orders keep the contact they were placed with."""
        self._check_own_contact(contact)
        if self.default_contact_id == contact:
            self.default_contact_id = False
        contact.active = False

    def set_default_contact(self, contact):
        self._check_own_contact(contact)
        self.default_contact_id = contact

    def set_citizen_id(self, citizen_id):
        """Record the citizen ID of an individual once; it is not asked again."""
        self.ensure_one()
        if self.citizen_id:
            raise UserError(self.env._("Your citizen ID is already registered."))
        if self.is_company:
            raise UserError(self.env._("A business is identified by its tax code, not a citizen ID."))
        value = (citizen_id or "").strip()
        if not value:
            raise UserError(self.env._("Enter your citizen ID."))
        self.citizen_id = value
