# The mixins are loaded first, because models of every concern inherit them.
from . import mixins

# isort: split
from . import (
    laboratory_files,
    management,
    master_data,
    notifications,
    sample_collection,
    signing,
    system,
    tasks,
    testing,
)
