def migrate(cr, version):
    # Older rows stored 0 for "no limit". A non-zero value is a limit; 0 stays unset.
    cr.execute(
        """
        UPDATE medilab_regulation_limit
           SET min_set = TRUE
         WHERE min_set IS NOT TRUE
           AND min_value IS NOT NULL
           AND min_value <> 0
        """
    )
    cr.execute(
        """
        UPDATE medilab_regulation_limit
           SET max_set = TRUE
         WHERE max_set IS NOT TRUE
           AND max_value IS NOT NULL
           AND max_value <> 0
        """
    )
