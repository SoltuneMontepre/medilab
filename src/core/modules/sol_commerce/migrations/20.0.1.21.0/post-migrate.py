def migrate(cr, _version):
    # A sample collection task kept its place in the note; the place now has its own field, shown on the calendar.
    cr.execute(
        """
        UPDATE medilab_task task
           SET place = task.note, note = NULL
          FROM medilab_task_type task_type
         WHERE task.type_id = task_type.id
           AND task_type.code = 'sample_collection'
           AND task.place IS NULL
           AND task.note IS NOT NULL
        """
    )
