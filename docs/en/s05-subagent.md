# s05 · Subagents: a fresh context for a side quest

> Code: [`agents/s05_subagent.py`](../../agents/s05_subagent.py) · [← s04](s04-todo.md) · Next: [s06 Skills →](s06-skills.md)

## The problem

"Find every place we call the payments API" might take 40 greps and file
reads and produce 200 KB of output. All of it stays in `messages` for the
rest of the session. It gets re-sent on every request, it slows the model down,
and it pushes the actual task out of view.

## The idea

A subagent is **the same loop with a new, empty `messages` list**.

```
parent ──task("find payment calls")──▶ child loop (fresh context)
       ◀──────── 5-line summary ──────  ...40 tool calls, then thrown away
```

```python
def run_subagent(description, prompt):
    sub_messages = [{"role": "user", "content": prompt}]   # <- the whole trick
    system = SUBAGENT_PROMPT.format(cwd=os.getcwd())
    summary = agent_loop(sub_messages, tools=SUB_TOOLS, system=system, depth=1, max_rounds=30)
    return summary
```

The parent only ever sees `summary`, as the result of its `task` tool call.
The 40 intermediate results are discarded together with `sub_messages`.

## Making the loop reusable

To run the loop twice, `agent_loop` now takes parameters:

```python
def agent_loop(messages, tools=None, system=None, depth=0, max_rounds=200):
```

- `tools`: children get `SUB_TOOLS`, which leaves out `task` (so they
  can't recurse forever) and `todo_write` (so they don't share the parent's plan).
- `system`: a prompt that tells the child **the summary is all the parent sees**.
  Without it, children reply "Done!" and the parent learns nothing.
- `max_rounds`: a runaway child must not burn the budget.

## Writing good task prompts

The child starts with **nothing**: no conversation history, no idea what the
user wants. The `task` tool description says so, and the parent has to
write a complete brief. That is the same skill as delegating to a
colleague: what to find, where to look, and what form the answer should take.

## When (not) to use one

Good fits: broad searches, "investigate why X", reading a large doc and
extracting three facts, independent changes in separate files.

Bad fits: small lookups (the overhead of a whole loop costs more than it
saves) and anything that needs the conversation so far.

## Run it

```bash
python agents/s05_subagent.py
```

The demo scaffolds a small project, then a subagent greps for TODOs. Watch
the indentation: the child's tool calls are nested, and
`subagent done (4 messages discarded)` is the context the parent never had to carry.

## Exercises

1. Run several `task` calls in parallel with threads. What has to change in the printing?
2. Give subagents a read-only tool set (`explore` type) vs. full (`general` type).
3. Track the tokens the child used and add them to a running total.
