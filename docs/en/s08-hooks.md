# s08 · Hooks: let your scripts steer the agent

> Code: [`agents/s08_hooks.py`](../../agents/s08_hooks.py) · [← s07](s07-compact.md) · Next: [s09 Memory →](s09-memory.md)

## The problem

"Always run the linter after editing." "Never touch `.env`." "Don't say
you're done until the tests pass." You can put all of this in the prompt.
The model will follow it most of the time, but "most of the time" isn't enough for these.

## The idea

A **hook** is a shell command the *harness* runs at fixed points in the loop.
The model can't skip it, forget it, or talk its way around it.

```json
// .harness/hooks.json
{
  "PreToolUse":       [{"matcher": "write_file|edit_file", "command": "python3 guard.py"}],
  "PostToolUse":      [{"matcher": "write_file|edit_file", "command": "ruff check --fix ."}],
  "UserPromptSubmit": [{"command": "git status --short"}],
  "Stop":             [{"command": "pytest -q"}]
}
```

| Event | Runs | Exit code 2 means |
|---|---|---|
| `UserPromptSubmit` | before the model sees your message | prompt is blocked |
| `PreToolUse` | before a tool runs | tool is **not** run; stderr goes to the model |
| `PostToolUse` | after a tool runs | stderr is appended to the result as feedback |
| `Stop` | when the model wants to finish | the model must keep working, with stderr as feedback |

## The contract

- The event is sent to the hook as **JSON on stdin**: `{"event", "cwd", "tool", "args", "output", ...}`.
- **Exit 0**: fine. Anything printed on stdout is passed to the model as context.
- **Exit 2**: block. stderr explains why.
- **Any other code**: the hook itself failed. The user is told, and the agent carries on.

That is the same contract Claude Code uses, so hooks written for one generally work with the other.

```python
def run_hooks(event, payload, target=""):
    for hook in hooks_for(event):
        if not matches(hook, target):
            continue
        r = subprocess.run(hook["command"], shell=True, input=json.dumps(payload), capture_output=True, text=True)
        if r.returncode == 2:
            return True, r.stderr.strip()     # blocked
        ...
```

## Feedback closes the loop

The demo installs a `PostToolUse` hook that runs `py_compile` on every
edited `.py` file. The scripted model writes a file with a missing
parenthesis:

```
⏺ write_file(path="greet.py", ...)
  ⚓ PostToolUse hook `python3 .harness/check_syntax.py` -> exit 2
  │ wrote 42 chars to greet.py
  │ <hook-feedback>
  │ File "greet.py", line 2 ...
The hook caught a missing parenthesis - fixing.
```

No one told the model to check syntax. The harness made it unavoidable.
That's the general pattern: **turn your quality bar into a hook and it is
enforced on every edit**.

## The `Stop` hook

`Stop` is the strongest of the four. A `pytest -q` stop hook means the agent
can't finish while tests fail. `MAX_STOP_BLOCKS = 3` stops a broken test suite from
trapping the agent forever.

## Run it

```bash
python agents/s08_hooks.py
```

## Exercises

1. Add a `PostToolUse` hook that runs your project's formatter.
2. Write a `PreToolUse` hook that blocks `git push` to `main`.
3. Add a `SessionStart` event that injects `git log --oneline -5`.
