# s07 · Context compaction: forgetting on purpose

> Code: [`agents/s07_compact.py`](../../agents/s07_compact.py) · [← s06](s06-skills.md) · Next: [s08 Hooks →](s08-hooks.md)

## The problem

Nothing ever leaves `messages`. Read ten files and you send all ten again
on every turn. Long sessions get slow and expensive, and then they hit the
context window and stop dead.

## Two layers of forgetting

**Layer 1: micro-compact (context > 50% of budget).**
Old, bulky tool outputs are replaced with a stub. The newest results stay intact.

```python
def micro_compact(messages):
    for m in [m for m in messages if m["role"] == "tool"][:-KEEP_RECENT]:
        if len(m["content"]) > 500 and not m["content"].startswith("[cleared"):
            m["content"] = f"[cleared: old {m['name']} output ({len(m['content'])} chars). Run the tool again if needed.]"
```

This is safe because tool outputs can be **regenerated**. If the model needs
that file again, it reads it again. The stub tells it so.

**Layer 2: full compact (context > budget, or the model asks).**
Save the whole transcript to disk, ask the model to summarize it, and
restart from the summary (simplified):

```python
def full_compact(messages):
    path = save_transcript(messages)                      # .harness/transcripts/*.jsonl
    summary = llm.chat(SUMMARY_PROMPT, [{"role": "user", "content": transcript}])["content"]
    messages[:] = [{"role": "user", "content":
        f"[compacted - full transcript saved at {path}]\n\nSummary of the session so far:\n{summary}\n\n"
        f"The user's latest request was:\n{last_request}\n\nContinue from here."}]
```

The summary prompt asks for what matters when you resume: goals,
decisions, **exact file paths**, commands that worked, errors and their
fixes, open todos, and the next step. A summary that says "we edited some
files" is useless.

The model can also trigger compaction itself through a `compact` tool, for
example between two unrelated tasks.

## The cache trade-off

s04 argued for append-only history. Compaction breaks that rule on purpose.
Editing an old message invalidates the provider's prompt cache from that
point on, so the next request pays full price for everything after it.

So compaction runs **only when a threshold is crossed**, and then in one batch.
Clearing a little every turn would invalidate the cache on every turn, which is
the worst of both. It's a real engineering trade-off, and production harnesses tune it carefully.

## Measuring

`estimate_tokens` uses about 4 characters per token. That's crude, but the
harness only needs to know which side of a threshold it is on. Real
harnesses read the exact `usage` numbers that come back with each API response.

## Run it

```bash
python agents/s07_compact.py
HARNESS_COMPACT_AT=20000 python agents/s07_compact.py   # small budget, with a real model
```

The demo reads a 1,200-line log in three chunks (wasteful on purpose), so
micro-compact clears the oldest read. Then the model calls `compact` and the
whole conversation collapses into a summary.

## Exercises

1. Use the real `usage` field from API responses instead of estimating.
2. Keep the last *N* messages verbatim after a full compact, not just the summary.
3. Add a `/transcript` command that greps old transcripts, so nothing is truly lost.
