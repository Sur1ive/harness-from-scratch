# s09 · Memory: AGENTS.md and notes that outlive a session

> Code: [`agents/s09_memory.py`](../../agents/s09_memory.py) · [← s08](s08-hooks.md) · Next: [s10 MCP →](s10-mcp.md)

## The problem

Every session starts from nothing. You explain again that tests run with
`make test`, that the staging DB is on port 5433, that you prefer plain
asserts. The model learned all of that yesterday and lost it when the process exited.

## Two cheap cures

**1. Project instructions are files.** Before the first request, the
harness reads:

```python
INSTRUCTION_FILES = [Path.home() / ".harness/AGENTS.md", Path("AGENTS.md"), Path("CLAUDE.md")]
```

and puts them in the system prompt. `AGENTS.md` is the cross-agent
convention, and `CLAUDE.md` is what Claude Code reads. Supporting both means
one file configures every agent your team uses.

**2. A memory tool.** The model decides something is worth keeping:

```python
def remember(note):
    with MEMORY_FILE.open("a") as f:      # .harness/memory.md
        f.write(f"- {note}\n")
```

The file is loaded into every future system prompt. That's all a
"long-term memory" has to be at this scale. There's no vector database and no
embeddings: a Markdown file that you can read, edit and commit.

```
<instructions file="AGENTS.md">
# Project notes
- Python 3.10+, standard library only.
- Run tests with: python3 -m unittest
</instructions>

<memory file=".harness/memory.md">
- User prefers pytest-style plain asserts in tests.
- Staging DB: localhost:5433.
</memory>
```

## Design notes

- **The model decides what to remember; the harness decides where it lives and when it's loaded.**
  The system prompt tells the model to save durable facts: conventions,
  preferences, gotchas. It shouldn't save the content of the current task.
- **Caps.** Instructions are capped at 20 KB, and only the last 10 KB of memory is loaded. A
  memory file that grows without limit becomes the next context problem.
- **Precedence.** User-level (`~/.harness/AGENTS.md`), then project-level. Real harnesses
  also load nested `AGENTS.md` files from subfolders when the agent works there.
- **It's in git.** Commit `AGENTS.md` and your whole team gets the same agent behaviour.

## Run it

```bash
python agents/s09_memory.py
```

## Exercises

1. Add a `forget(pattern)` tool, and decide whether it should need permission.
2. Load `AGENTS.md` from every parent folder up to the git root.
3. Ask the model to tidy `memory.md` (merge duplicates, drop stale facts) when it passes 50 lines.
