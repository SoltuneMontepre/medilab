"""The values of a result Medilab Mobile enters or changes, as the result's fields hold them."""

# The result's field each value of the phone's request sets.
PHONE_RESULT_FIELDS = {
    "value": "value",
    "value_text": "value_text",
    "decimals": "value_decimals",
    "conclusion": "conclusion",
}


def phone_result_values(values):
    """The fields the request sets, by the values it sends: a number, its decimals, a text and a conclusion; null
    clears a text or a conclusion."""
    return {
        field: values[name] if values[name] is not None else (0.0 if name == "value" else False)
        for name, field in PHONE_RESULT_FIELDS.items()
        if name in values
    }
