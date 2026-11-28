def migrate(cr, _version):
    cr.execute(
        """
        UPDATE medilab_test_request
           SET status = 'confirmed'
         WHERE status IN ('paid', 'on_credit')
        """
    )
    cr.execute(
        """
        UPDATE medilab_task task
           SET planned_end = task.planned_start + INTERVAL '60 minutes'
          FROM medilab_task_type task_type
         WHERE task.type_id = task_type.id
           AND task_type.code = 'sample_collection'
           AND task.status IN ('open', 'assigned', 'in_progress')
           AND task.planned_start IS NOT NULL
           AND task.planned_end IS NULL
        """
    )
