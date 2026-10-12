# s06 · Skills: knowledge on demand

> Code: [`agents/s06_skills.py`](../../agents/s06_skills.py) · [← s05](s05-subagent.md) · Next: [s07 Compaction →](s07-compact.md)

## The problem

Your team has a commit message convention, a code review checklist, a
guide for writing tests, and a deploy runbook. Put all of it in the system
prompt and every request pays for 20 KB of instructions that matter maybe
5% of the time. Worse, the model has to work out which parts apply right now.

## The idea: progressive disclosure

```
system prompt   one line per skill: name + "use when ..."     ~100 tokens
load_skill()    the full SKILL.md, only when it's relevant    on demand
```

The model sees a table of contents and loads a chapter only when it needs it.

## What a skill is

A folder with a `SKILL.md`: YAML front matter, then Markdown.

```markdown
---
name: commit-message
description: Write a clear git commit message (Conventional Commits). Use when the user asks to commit, or to write/fix a commit message.
---

# Writing commit messages

1. Look at what actually changed first: `git status` and `git diff --staged` ...
```

The `description` does the routing, so it should say **when** to use the
skill, not only what it is. This repo ships three examples in
[`skills/`](../../skills).

It's the same format Claude Code and other agents read, so a skill written
once works across harnesses. s06 looks in these folders, and the first
match wins:

```python
SKILL_DIRS = [
    Path(".harness/skills"), Path(".claude/skills"), Path(".agents/skills"),
    Path.home() / ".harness/skills",
    Path(__file__).resolve().parent.parent / "skills",   # the bundled examples
]
```

## The code

Three small functions:

```python
def skills_index():          # goes into the system prompt
    return "\n\nSkills (load with load_skill):\n" + "\n".join(
        f"- {name}: {s['description']}" for name, s in find_skills().items())

def load_skill(name):        # a tool the model calls
    skill = find_skills().get(name)
    return f"<skill name=\"{name}\" dir=\"{skill['dir']}\">\n{skill['body']}\n</skill>"
```

`load_skill` returns the skill as a **tool result**, so it lands at the end
of the context, right next to the task it's about.

## Skills vs. the alternatives

| | Always in context? | Who decides to use it? |
|---|---|---|
| System prompt / `AGENTS.md` (s09) | yes | always applies |
| Skill | only its one-line description | the model |
| Subagent (s05) | no, separate context | the model |
| Hook (s08) | no | the harness, deterministically |

Rule of thumb: things that apply to every task go in `AGENTS.md`. Procedures
for particular kinds of task are skills.

## Run it

```bash
python agents/s06_skills.py
```

## Exercises

1. Let a skill bundle scripts: if `SKILL.md` mentions `scripts/lint.sh`, the model should be able to run it.
2. Add a `/skill <name>` command that force-loads a skill (`harness.py` already has `/skills` to list them).
3. Write a skill for your own team's conventions and test it with a real model.
