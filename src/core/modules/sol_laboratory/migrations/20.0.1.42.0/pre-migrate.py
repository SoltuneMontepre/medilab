def migrate(cr, _version):
    # A sample that cannot be tested is recorded as unusable, on arrival and on its handover records.
    cr.execute("UPDATE medilab_sample SET condition = 'unusable' WHERE condition = 'damaged'")
    cr.execute("UPDATE medilab_handover_record_sample SET condition = 'unusable' WHERE condition = 'damaged'")
