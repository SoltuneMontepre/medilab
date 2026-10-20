# The operation the dialogs below inherit is loaded first.
from . import stock_operation

# isort: split
from . import (
    container_opening,
    container_scan,
    res_config_settings,
    result_container,
    scheduled_job,
    stock_correction,
    stock_lot,
    stock_move,
    stock_package,
    stock_quant,
    stock_relocation,
    stock_scrap_reason_tag,
    stock_use,
    test_result,
)
