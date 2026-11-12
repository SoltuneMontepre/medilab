"""How the expected samples of one sample are shown."""


def sampling_entry(sample, sample_type, objects, rows, missing):
    """One sample's expected samples as the expected sampling template shows them: its objects, its sampling groups
    with their amounts in each unit, and the methods that state no sampling requirement.

    Each row has its group number, container type, preservation, amount, unit and methods.
    """
    groups = {}
    for row in rows:
        group = groups.setdefault(
            row["group"],
            {
                "container_type": row["container_type"],
                "preservation": row["preservation"],
                "amounts": [],
                "methods": row["methods"].browse(),
            },
        )
        group["amounts"].append((row["amount"], row["unit"]))
        group["methods"] |= row["methods"]
    return {
        "name": sample.customer_sample_name or sample_type.name,
        "sample_type": sample_type,
        "objects": objects,
        "expected": objects * len(groups),
        "groups": [groups[number] for number in sorted(groups)],
        "missing": missing,
    }
