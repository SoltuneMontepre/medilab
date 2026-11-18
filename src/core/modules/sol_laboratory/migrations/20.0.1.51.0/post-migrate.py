def migrate(cr, _version):
    # A message the phone posted in a conversation is a discussion message, not an internal note.
    cr.execute(
        """
        UPDATE mail_message message
           SET subtype_id = comment.res_id
          FROM ir_model_data comment, ir_model_data note
         WHERE comment.module = 'mail' AND comment.name = 'mt_comment'
           AND note.module = 'mail' AND note.name = 'mt_note'
           AND message.subtype_id = note.res_id
           AND message.model = 'discuss.channel'
           AND message.message_type = 'comment'
           AND message.posted_by_device_id IS NOT NULL
        """
    )
