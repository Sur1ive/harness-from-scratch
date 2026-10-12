# s03 · Permissions

> Code: [`agents/s03_permissions.py`](../../agents/s03_permissions.py) · [← s02](s02-tools.md) · Next: [s04 Todos →](s04-todo.md)

## The problem

The model can run any shell command. Models misread instructions, follow
injected text in a README they just read, and occasionally decide that
`rm -rf build/ ~/old` is a cleanup. A system prompt saying "be careful" is
not a security boundary.

## The idea

The harness checks **every** tool call before it runs, in a fixed order:

```
1. deny rules    sudo, rm -rf /, curl | sh, mkfs, fork bombs    -> always refused
2. read-only?    read_file, glob, grep                          -> always allowed
3. mode          auto: allow everything / plan: refuse all writes
4. ask a human   y / n / a(lways) / or type feedback
```

```python
def check_permission(name, args):
    """None = go ahead. A string = the reason it was refused (sent to the model)."""
    if name == "bash":
        for rule in DENY_RULES:
            if re.search(rule, args.get("command", "")):
                return f"Denied by a safety rule ({rule}). Do not try to work around it."
    if name in READ_ONLY or MODE == "auto" or name in always_allow:
        return None
    if MODE == "plan":
        return "Denied: plan mode is read-only. Describe the change instead of making it."
    answer = ask_human(name, args)
    ...
```

## A "no" is feedback

The key move: a refusal is **not an exception**. It's returned as the tool
result:

```
⏺ write_file(path="hello.md", ...)
  allow write_file? [y/n/a/feedback] put it in docs/ instead
  │ Denied by the user, who says: put it in docs/ instead
⏺ write_file(path="docs/hello.md", ...)
```

The model reads the reason and adjusts. Without this, permission prompts
are just an off switch; with it, they become a way to steer the agent while it works.

## The three modes

| `HARNESS_PERMISSION` | Behaviour | When |
|---|---|---|
| `ask` (default) | read freely, ask before writing or running | normal use |
| `auto` | allow everything except deny rules | sandboxes, CI, throwaway VMs |
| `plan` | read-only, every write is refused | "look around and propose a plan first" |

Plan mode costs one line of code, and it is one of the most useful features
in real harnesses. You get an investigation and a plan before anything changes.

## What this does *not* protect against

Deny rules are regexes, and `bash` is Turing-complete. `s"u"do`,
`python -c "import shutil; ..."` or a script the model writes and then runs will
get past any pattern list. Treat deny rules as a guard against
*accidents*. The real boundary against a hostile model is a sandbox: a
container, a VM, or OS-level sandboxing. Production harnesses layer all of these.

## Run it

```bash
python agents/s03_permissions.py                         # demo: a sudo is blocked, a write gets redirected
HARNESS_PERMISSION=plan python agents/s03_permissions.py # with a real key: try asking for a change
```

## Exercises

1. Add an allow-list: `git status`, `git diff`, `ls` and `pytest` run without asking.
2. Remember "always" decisions per *command prefix* (`npm test`) instead of per tool.
3. Show a diff preview before approving `edit_file`.
