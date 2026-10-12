# s02 · Tools

> Code: [`agents/s02_tools.py`](../../agents/s02_tools.py) · [← s01](s01-agent-loop.md) · Next: [s03 Permissions →](s03-permissions.md)

## The problem

With only `bash`, the model edits files with `sed -i 's/.../.../'` and reads
them with `cat`. That means escaping bugs, 5 MB outputs, and files written
outside the project by accident.

## The idea

Keep a table that maps each **tool name** to the **schema the model sees**
and the **Python handler that runs**. The loop doesn't change; it just looks up the handler.

```python
HANDLERS = {
    "bash": run_bash,
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "glob": glob_files,
    "grep": grep,
}

def run_tool(name, args):
    handler = HANDLERS.get(name)
    if handler is None:
        return f"Error: unknown tool {name}"
    try:
        return str(handler(**args))
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
```

The `except` is the most important line in the chapter: **tool errors are
results, not crashes.** "File not found" goes back to the model, which then
runs `glob` and finds the right path. Agents look smart largely because they
recover from their own mistakes, and they can only do that if they get to see them.

## Design choices worth copying

**`edit_file` replaces one exact, unique snippet.**

```python
count = text.count(old)
if count != 1:
    return f"Error: `old` must appear exactly once in {path}, found {count} times. Add more context."
```

No line numbers (they drift as soon as you edit) and no regex (escaping).
If the snippet is ambiguous the model is told to add context, which works
remarkably well. Claude Code's `Edit` tool works the same way.

**`read_file` returns line numbers and a window.** Big files come back in
slices of 400 lines, with a hint of how to read the next slice. The model
never gets a 2 MB file it didn't ask for.

**`safe_path` keeps every file tool inside the workspace.**

```python
def safe_path(p):
    root = Path.cwd().resolve()
    path = (root / p).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"path escapes the workspace: {p}")
    return path
```

`../../etc/passwd` and `/tmp/x` are refused. (`bash` can still do anything,
and s03 deals with that.)

**Descriptions are prompts.** "Read a file before editing it" and "prefer
`grep` over `bash grep`" live in the system prompt and tool descriptions.
Tool descriptions are among the most-read text in the whole context, so
write them as carefully as code.

## Run it

```bash
python agents/s02_tools.py
```

The demo writes `fizzbuzz.py`, runs it, edits one string and verifies the
change with `grep`. Every step is a real tool call.

## Exercises

1. Add a `list_dir` tool. You'll need to touch two places: `TOOLS` and `HANDLERS`.
2. Make `edit_file` accept `replace_all: true`.
3. Make `read_file` refuse binary files with a helpful message.
