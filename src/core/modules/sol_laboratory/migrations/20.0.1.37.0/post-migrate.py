def migrate(cr, _version):
    # A sample test approved before keeps its first approval: the last standing signature of its earliest approved
    # result, which a correction leaves standing.
    cr.execute(
        """
        UPDATE medilab_sample_test test SET first_approved_at = approval.approved_at
          FROM (
                SELECT result.sample_test_id, MIN(signed.at) AS approved_at
                  FROM medilab_test_result result
                  JOIN LATERAL (
                        SELECT MAX(signature.create_date) AS at
                          FROM medilab_signature signature
                         WHERE signature.document_model = 'medilab.test.result'
                           AND signature.document_id = result.id
                           AND signature.document_version = result.document_version
                           AND signature.decision = 'signed'
                           AND signature.withdrawn_at IS NULL
                       ) signed ON TRUE
                 WHERE result.status = 'approved'
                 GROUP BY result.sample_test_id
               ) approval
         WHERE approval.sample_test_id = test.id
           AND approval.approved_at IS NOT NULL
           AND test.first_approved_at IS NULL
        """
    )
    # A test cancelled with its sample or request got no time; its last change is when that happened.
    cr.execute(
        """
        UPDATE medilab_sample_test SET cancelled_at = write_date
         WHERE status = 'cancelled' AND cancelled_at IS NULL
        """
    )
