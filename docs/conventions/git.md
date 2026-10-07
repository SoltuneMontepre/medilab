# Git

How branches and pull requests are named. A branch or pull request that does not match fails CI.

## Branch names

A branch is `main`, a `revert-` branch, or a type followed by a slash and a description:

```text
<type>/<description>
```

| Type              | Use for                      |
| ----------------- | ---------------------------- |
| `feat`, `feature` | A new capability             |
| `fix`             | A bug fix                    |
| `docs`            | Documentation only           |
| `refactor`        | A change that keeps behavior |
| `chore`           | Maintenance                  |
| `task`            | Any other planned work       |

- The description is not empty: `feat/customer-portal`, `fix/quotation-vat`.
- A branch that reverts a change starts with `revert-`: `revert-customer-portal`.

The check is the pattern `^(main$|revert-.+|(feat|fix|docs|refactor|chore|task|feature)\/.+)$`.

## Pull request titles

A pull request title is a type in square brackets, an optional issue number, then the title. The title starts with a letter:

```text
[<type>] <title>
[<type>] | #<issue> <title>
```

Allowed types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `style`, `perf`, `build`, `ci`.

Examples:

- `[feat] Add customer portal login`
- `[fix] | #42 Correct VAT on quotations`
- `[ci] Publish Terraform secrets`

The check is the pattern `^\[(feat|fix|chore|docs|refactor|test|style|perf|build|ci)\](\s*\|\s*#\d+)?\s+[a-zA-Z].+`.

## Related documents

- [Taskfiles](taskfiles.md)
- [Documentation](documentation.md)
