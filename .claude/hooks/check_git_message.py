"""Block commits and pull requests whose title breaks docs/conventions/git.md or that carry attribution lines."""

import json
import re
import sys
from pathlib import Path

TITLE_PATTERN = re.compile(r"^\[(feat|fix|chore|docs|refactor|test|style|perf|build|ci)\](\s*\|\s*#\d+)?\s+[a-zA-Z].+")
GIT_GENERATED_TITLE = re.compile(r"^(Merge |Revert \")")
ATTRIBUTION_PATTERN = re.compile(r"co-authored-by:|generated with \[?claude code|\U0001f916", re.IGNORECASE)
COMMIT_PATTERN = re.compile(r"\bgit\s+(?:-c\s+\S+\s+)*commit\b")
PR_PATTERN = re.compile(r"\bgh\s+pr\s+(create|edit)\b")
HEREDOC_START = re.compile(r"""\$\(\s*cat\s+<<-?\s*['"]?(\w+)['"]?[^\n]*\n""")


def read_value(text):
    """Return the argument at the start of text, unwrapping quotes, heredocs and PowerShell here-strings."""
    text = text.lstrip(" =")
    if text[:2] in ("\\'", '\\"'):
        return text[2:].split(text[:2], 1)[0]
    heredoc = HEREDOC_START.match(text.lstrip("\"'"))
    if heredoc:
        body = text.lstrip("\"'")[heredoc.end() :]
        return body.split(f"\n{heredoc.group(1)}", 1)[0]
    if text[:2] in ("@'", '@"'):
        body = text[2:].split("\n", 1)[-1]
        return re.split(r"\n['\"]@", body, maxsplit=1)[0]
    if text[:1] in ("'", '"'):
        quote = text[0]
        match = re.match(rf"{quote}((?:\\.|[^{quote}\\])*){quote}", text, re.DOTALL)
        return match.group(1) if match else text[1:]
    return text.split(None, 1)[0] if text.strip() else ""


def flag_value(command, flags):
    """Return the value of the first of flags in command, or None when none is given."""
    match = re.search(rf"(?:^|\s)(?:{'|'.join(flags)})(?=[\s=])", command)
    return read_value(command[match.end() :]) if match else None


def first_line(message):
    """Return the first non-empty line of message."""
    return next((line.strip() for line in message.splitlines() if line.strip()), "")


def commit_title(command):
    """Return the title of a git commit command, or None when it is not given on the command line."""
    message = flag_value(command, ["-m", "--message"])
    if message is not None:
        return first_line(message)
    text = read_file(flag_value(command, ["-F", "--file"]))
    return first_line(text) if text else None


def to_path(value):
    """Return value as a path, turning a Git Bash path such as /c/Users into C:/Users on Windows."""
    if sys.platform == "win32":
        value = re.sub(r"^/([a-zA-Z])/", r"\1:/", value)
    return Path(value)


def read_file(value):
    """Return the text of the file at value, or an empty string when there is none."""
    path = to_path(value) if value else None
    return path.read_text(encoding="utf-8") if path and path.is_file() else ""


def message_files(command):
    """Return the contents of the message and body files the command passes."""
    return read_file(flag_value(command, ["-F", "--file", "--body-file"]))


def problems(command):
    """List what the command breaks."""
    found = []
    is_commit = COMMIT_PATTERN.search(command)
    is_pr = PR_PATTERN.search(command)
    if (is_commit or is_pr) and ATTRIBUTION_PATTERN.search(command + message_files(command)):
        found.append("Remove co-author and attribution lines; AGENTS.md forbids them in commits and pull requests.")
    if is_commit:
        title = commit_title(command[is_commit.end() :])
        if title and "$" not in title and not TITLE_PATTERN.match(title) and not GIT_GENERATED_TITLE.match(title):
            found.append(f"Commit title '{title}' must be '[<type>] <title>' as in docs/conventions/git.md.")
    if is_pr:
        title = flag_value(command[is_pr.end() :], ["--title", "-t"])
        title = first_line(title) if title else None
        if title and "$" not in title and not TITLE_PATTERN.match(title):
            found.append(f"Pull request title '{title}' must be '[<type>] <title>' as in docs/conventions/git.md.")
    return found


def main():
    """Read the tool call from stdin and exit with 2 to block it when it breaks a rule."""
    command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    found = problems(command)
    if found:
        print("\n".join(found), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
