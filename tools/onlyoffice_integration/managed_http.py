"""Bounded HTTP sessions with separate cookies and no inherited proxy credentials."""

import json
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, _request, _file, _code, _message, _headers, _url):
        return None


class Response:
    def __init__(self, response):
        self.status_code = response.code
        self.content = response.read(10 * 1024 * 1024 + 1)
        if len(self.content) > 10 * 1024 * 1024:
            raise ValueError("The managed proof response exceeds its size bound.")

    @property
    def text(self):
        return self.content.decode("utf-8")

    def json(self):
        return json.loads(self.content)


class HttpSession:
    def __init__(self):
        self.cookies = CookieJar()
        self.proxy = ProxyHandler({})
        self.opener = build_opener(
            self.proxy, HTTPCookieProcessor(self.cookies), NoRedirect()
        )

    def request(
        self,
        method,
        url,
        *,
        json_body=None,
        data=None,
        headers=None,
        timeout=20,
        allow_redirects=False,
    ):
        if allow_redirects:
            raise ValueError("The managed probe refuses automatic HTTP redirects.")
        headers = dict(headers or {})
        if json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        elif isinstance(data, dict):
            data = urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=timeout)
        except HTTPError as error:
            response = error
        with response:
            return Response(response)

    def get(self, url, **options):
        return self.request("GET", url, **options)

    def post(self, url, **options):
        return self.request("POST", url, **options)

    def put(self, url, **options):
        return self.request("PUT", url, **options)
