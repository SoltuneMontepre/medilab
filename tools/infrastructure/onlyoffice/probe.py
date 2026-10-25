"""Emit only fixed health states; URLs and exception details never enter logs."""

import ssl
import sys
import time
import urllib.error
import urllib.request

URL = "https://onlyoffice.medilab.svc.cluster.local/healthcheck"


def healthy(url=URL, cafile="/run/onlyoffice-ca/ca.crt"):
    context = ssl.create_default_context(cafile=cafile)
    # Do not follow redirects to an unapproved origin or use inherited proxy credentials.

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=context)
    )
    try:
        with opener.open(url, timeout=5) as response:
            return response.status == 200 and response.read(16).strip() == b"true"
    except (OSError, urllib.error.URLError):
        return False


if __name__ == "__main__":
    while True:
        try:
            state = int(healthy())
        except (OSError, ValueError, ssl.SSLError):
            state = 0
        sys.stdout.write(f"onlyoffice_probe healthy={state}\n")
        sys.stdout.flush()
        time.sleep(30)
