---
name: commit-message
description: Write a clear git commit message (Conventional Commits). Use when the user asks to commit, or to write/fix a commit message.
---

# Writing commit messages

1. Look at what actually changed first: `git status` and `git diff --staged`
   (or `git diff` if nothing is staged). Never describe changes you have not seen.
2. Subject line: `<type>(<optional scope>): <summary>`
   - type: feat | fix | docs | refactor | test | perf | build | ci | chore
   - imperative mood ("add", not "added"), no trailing period, <= 72 chars
3. Blank line, then a body only if the *why* is not obvious from the subject.
   Wrap at 72 columns. Explain motivation and trade-offs, not the diff line by line.
4. Breaking changes: add `!` after the type and a `BREAKING CHANGE:` footer.
5. One logical change per commit. If the diff mixes two, suggest splitting it.

Examples:

    fix(ship): retry once on network timeout

    feat(api)!: drop the v1 /payments endpoint

    BREAKING CHANGE: clients must call /v2/payments.
