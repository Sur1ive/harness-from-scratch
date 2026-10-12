# Notes for coding agents working on this repo

(Yes, `agents/s09_memory.py` and `agents/harness.py` load this file too.)

- Python 3.10+, **standard library only**. Never add a dependency.
- Each `agents/sXX_*.py` is a complete, standalone, runnable file. Chapters do
  not import each other; only `agents/llm.py` is shared. A change to a
  mechanism usually has to be applied to every later chapter too.
- New code in a chapter is marked with a `# -- NEW in sXX` section header.
- Keep each chapter's offline demo (`DEMO`) working. Run all tests with:
  `python tests/test_harness.py`
- Docs live in `docs/en/` and `docs/zh/`. Keep both languages in sync.
