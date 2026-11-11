"""In-process synchronization markers; JSON-RPC context values cannot impersonate them."""

CALENDAR_SYNC_CONTEXT = "medilab_skip_calendar_sync"
CALENDAR_SYNC_TOKEN = object()
# The scheduler has already checked the slot before writing its times.
SCHEDULING_CONTEXT = "medilab_scheduling"
SCHEDULING_TOKEN = object()
