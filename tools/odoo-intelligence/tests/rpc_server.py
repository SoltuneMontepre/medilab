"""A separate process exercises transport errors without depending on OdooLS."""

import os
import sys

from odoo_intelligence.transport import read_message, write_message

while True:
    message = read_message(sys.stdin.buffer)
    if message is None:
        break
    method = message.get("method")
    if method == "exit":
        break
    if method == "die":
        os._exit(0)
    if method == "hang" or "id" not in message:
        continue
    response = {"jsonrpc": "2.0", "id": message["id"]}
    if method == "reject":
        response["error"] = {"code": -32602, "message": "rejected"}
    else:
        response["result"] = message.get("params")
    write_message(sys.stdout.buffer, response)
