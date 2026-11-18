def migrate(cr, _version):
    # A handover record names the signed-in phone it was signed on, not the phone's push token.
    cr.execute(
        "ALTER TABLE medilab_handover_record DROP CONSTRAINT IF EXISTS medilab_handover_record_signed_device_id_fkey"
    )
    cr.execute(
        """
        UPDATE medilab_handover_record record
           SET signed_device_id = token.laboratory_device_id
          FROM medilab_mobile_device token
         WHERE token.id = record.signed_device_id
        """
    )
