"""Read protected inventory using an approved existing session, without attempting authentication."""

import hashlib
import http.cookiejar
import json
import urllib.request


def inventory(cookie_file, expected_identifier):
    cookies = http.cookiejar.MozillaCookieJar(cookie_file)
    cookies.load(ignore_discard=True, ignore_expires=False)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    query = """{
      serverConfig { configurationMode }
      activeUser { userId isAnonymous }
      listUsers(page: {}, filter: {}) { userId authRole grantedTeams enabled }
      listTeams { teamId }
      userConnections(projectId: "g_GlobalConfiguration") { id name }
    }"""
    request = urllib.request.Request(
        "https://cloudbeaver.soltunemontepre.tech/api/gql",
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with opener.open(request, timeout=10) as response:
        body = json.load(response)
    data = body.get("data") or {}
    active = data.get("activeUser") or {}
    users = data.get("listUsers")
    teams = data.get("listTeams")
    connections = data.get("userConnections")
    mode = (data.get("serverConfig") or {}).get("configurationMode")
    if (
        body.get("errors")
        or active.get("isAnonymous") is not False
        or not isinstance(active.get("userId"), str)
        or not isinstance(users, list)
        or not isinstance(teams, list)
        or not isinstance(connections, list)
        or not isinstance(mode, bool)
        or not any(user.get("userId") == active["userId"] and user.get("enabled") is True for user in users)
    ):
        raise RuntimeError("Approved application session could not verify persistent accounts; no login was attempted.")
    return {
        "verified": True,
        "configuration_mode": mode,
        "users": len(users),
        "teams": len(teams),
        "connections": len(connections),
        "inventory_sha256": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
        "active_identifier_matches_secret": active["userId"] == expected_identifier.lower(),
    }
