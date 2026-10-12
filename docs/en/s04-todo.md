# s04 · Todos: let the model plan

> Code: [`agents/s04_todo.py`](../../agents/s04_todo.py) · [← s03](s03-permissions.md) · Next: [s05 Subagents →](s05-subagent.md)

## The problem

Give a model a ten-step task. Around step six it gets absorbed in a failing
test, fixes it, and announces it is done. Steps seven to ten are forgotten.
The plan only ever existed in the model's head, and it is now buried 30 tool results up.

## The idea

A tool that does almost nothing: it stores a checklist and shows it back.

```python
todo_write(items=[
    {"content": "Write calc.py with add() and sub()", "status": "in_progress"},
    {"content": "Write test_calc.py",                 "status": "pending"},
    {"content": "Run the tests",                      "status": "pending"},
])
```
```
[>] Write calc.py with add() and sub()
[ ] Write test_calc.py
[ ] Run the tests
(0/3 done)
```

Writing the plan down makes the model commit to it, and every update puts
the remaining steps back at the *end* of the context, which is where the model pays the most attention.

## Two harness rules

**One item in progress at a time.**

```python
if sum(i["status"] == "in_progress" for i in clean) > 1:
    raise ValueError("only one item may be in_progress at a time")
```

This forces sequential focus, and the error goes back to the model like any other tool error.

**A nag when the plan goes stale.** If the model goes three rounds without
touching its list while items are open, the harness adds a reminder to
the newest tool result:

```python
if TODOS.open_items() and rounds_since_todo >= NAG_AFTER:
    messages[-1]["content"] += "\n\n<reminder>You have open todos. Update your list with todo_write.</reminder>"
```

## Why append, not insert?

We could insert the reminder as a new system message or rewrite the system
prompt. We don't, because **history is append-only**. Providers cache the
prompt prefix; everything before the first changed byte is reused cheaply.
Editing the system prompt or an old message invalidates the cache from that
point on. Appending to the newest message, which hasn't been sent yet,
costs nothing.

This idea shows up throughout the harness. When you want to tell the model
something mid-task, attach it to what you are about to send anyway.

## Run it

```bash
python agents/s04_todo.py
```

Watch the demo skip its updates for three rounds, get nagged, and then complete the list.

## Exercises

1. Show the todo list in the terminal after every update as a one-line progress bar.
2. Reject a todo list where something is marked completed but was never in_progress. Is that too strict?
3. Persist the list to `.harness/todos.json` so it survives a restart.
