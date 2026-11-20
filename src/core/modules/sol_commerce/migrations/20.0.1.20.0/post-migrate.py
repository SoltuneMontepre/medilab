def migrate(cr, _version):
    # Requests that confirmed orders created keep what the customer agreed on their samples.
    cr.execute(
        """
        UPDATE medilab_test_request request SET from_order = TRUE
          FROM sale_order o
         WHERE o.test_request_id = request.id AND request.from_order IS NOT TRUE
        """
    )
