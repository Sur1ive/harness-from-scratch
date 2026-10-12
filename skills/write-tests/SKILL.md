---
name: write-tests
description: Add focused unit tests for existing code. Use when the user asks for tests or coverage.
---

# Writing tests

1. Find the project's test setup before writing anything: look for
   `pytest.ini`, `pyproject.toml`, `package.json` scripts, an existing
   `tests/` folder. Match its framework, file naming, and style.
2. For each function under test cover: the normal case, the edges
   (empty, zero, one, max), and the error path.
3. One behaviour per test; the test name says what it checks
   (`test_sub_returns_negative_when_b_larger`).
4. No network, no sleeps, no real clock - fake them.
5. Run the tests. Then break the code on purpose (flip an operator) and
   confirm a test fails; restore it. A test that can't fail is worthless.
6. Report: files added, how to run them, what is still untested.
