"""The language of text the system writes for staff: task names and internal notes."""

# The laboratory works in Vietnamese; staff read what the system writes in it when it is installed.
STAFF_LANGUAGE = "vi_VN"


def staff_lang(env, user=None):
    """The staff member's own language when known, else Vietnamese when installed, else the company's. A customer
    acting on the portal must not decide the language of what the laboratory reads."""
    if user and user.lang:
        return user.lang
    if env["res.lang"]._get_data(code=STAFF_LANGUAGE).id:
        return STAFF_LANGUAGE
    return env.company.partner_id.lang or env.lang


def staff_env(env, user=None):
    """The environment that writes in the staff language."""
    return env(context=dict(env.context, lang=staff_lang(env, user)))
