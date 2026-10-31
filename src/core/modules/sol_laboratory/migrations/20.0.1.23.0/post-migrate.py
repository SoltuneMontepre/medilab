def migrate(cr, _version):
    # A level replaced or removed during signing keeps its position among archived levels, so only active levels are
    # unique by position now.
    cr.execute("ALTER TABLE medilab_approval_level DROP CONSTRAINT IF EXISTS medilab_approval_level_sequence_unique")
