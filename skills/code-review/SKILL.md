---
name: code-review
description: Review a diff or files for bugs before style. Use when the user asks for a review, a second look, or "is this ok?".
---

# Code review

Read the change in full before commenting. Then go through, in this order:

1. **Correctness** - wrong logic, off-by-one, unhandled `None`/empty input,
   wrong error handling, race conditions, resource leaks.
2. **Security** - injection (SQL, shell, path traversal), secrets in code,
   missing auth checks, unsafe deserialization.
3. **Tests** - is the new behaviour tested? Would the tests fail if the code broke?
4. **Design** - duplicated logic, functions doing two jobs, names that lie.
5. **Style** - only if it hurts readability. Never nitpick what a formatter fixes.

For every finding give: `file:line`, what goes wrong (a concrete input and
the wrong result), and a suggested fix. Lead with the most severe.
If you find nothing serious, say so plainly - don't invent issues.
