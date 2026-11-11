# Context key set while a parameter saves its ways of testing and their sample types together: the parameter checks the
# default of each parameter and sample type once all of them are saved.
DEFAULTS_CHECKED_BY_PARAMETER = "medilab_defaults_checked_by_parameter"
# The value of that key: an object no RPC client can send, so a client cannot skip the check.
DEFAULTS_CHECKED = object()
# Context key set while a confirmed order creates its samples: the customer accepted their regulations, which the samples
# keep even when one is no longer in force.
REGULATIONS_ACCEPTED = "medilab_regulations_accepted"
# The value of that key: an object no RPC client can send, so a client cannot skip the check.
ACCEPTED = object()
