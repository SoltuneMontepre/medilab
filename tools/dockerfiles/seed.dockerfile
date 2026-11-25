# The seeded demo database of Claude Code cloud sessions: the volume tar files and commit that task cloud:seed writes.
# Build it with that directory as the context; task cloud:start copies /seed out of a container of it.
FROM scratch

COPY . /seed/
