# s08 · 钩子：让你的脚本给 agent 定规矩

> 代码：[`agents/s08_hooks.py`](../../agents/s08_hooks.py) · [← s07](s07-compact.md) · 下一章：[s09 记忆 →](s09-memory.md)

## 问题

"改完代码一定要跑 linter。""绝不能碰 `.env`。""测试没过不许说完成。"
这些都可以写进提示词，模型大多数时候也会照做。但对这类要求来说，"大多数时候"不够。

## 思路

**钩子**是 *harness* 在循环的固定节点上执行的 shell 命令。模型没法跳过、没法忘记，也没法说服它网开一面。

```json
// .harness/hooks.json
{
  "PreToolUse":       [{"matcher": "write_file|edit_file", "command": "python3 guard.py"}],
  "PostToolUse":      [{"matcher": "write_file|edit_file", "command": "ruff check --fix ."}],
  "UserPromptSubmit": [{"command": "git status --short"}],
  "Stop":             [{"command": "pytest -q"}]
}
```

| 事件 | 触发时机 | 退出码 2 的含义 |
|---|---|---|
| `UserPromptSubmit` | 模型看到你的消息之前 | 拦下这条消息 |
| `PreToolUse` | 工具执行之前 | **不执行**该工具，stderr 发给模型 |
| `PostToolUse` | 工具执行之后 | stderr 作为反馈附到结果后面 |
| `Stop` | 模型想要结束时 | 模型必须继续干活，stderr 作为反馈 |

## 约定

- 事件以 **JSON 形式通过 stdin** 传给钩子：`{"event", "cwd", "tool", "args", "output", ...}`
- **退出码 0**：没问题；stdout 里打印的内容会作为上下文传给模型
- **退出码 2**：拦截；stderr 说明原因
- **其他退出码**：钩子自己出错了，告知用户，agent 照常继续

这和 Claude Code 的约定一致，所以为其中一个写的钩子，一般也能用在另一个上。

```python
def run_hooks(event, payload, target=""):
    for hook in hooks_for(event):
        if not matches(hook, target):
            continue
        r = subprocess.run(hook["command"], shell=True, input=json.dumps(payload), capture_output=True, text=True)
        if r.returncode == 2:
            return True, r.stderr.strip()     # 被拦截
        ...
```

## 反馈让循环闭合

演示安装了一个 `PostToolUse` 钩子，对每个被修改的 `.py` 文件跑 `py_compile`。脚本里的模型写了一个少了右括号的文件：

```
⏺ write_file(path="greet.py", ...)
  ⚓ PostToolUse hook `python3 .harness/check_syntax.py` -> exit 2
  │ wrote 42 chars to greet.py
  │ <hook-feedback>
  │ File "greet.py", line 2 ...
The hook caught a missing parenthesis - fixing.
```

没人叫模型去检查语法，是 harness 让检查变得无法回避。这就是通用模式：**把你的质量标准写成钩子，每次修改都会被强制执行**。

## `Stop` 钩子

`Stop` 是四种钩子里最强的。挂一个 `pytest -q` 作为 Stop 钩子，测试不过，agent 就不能收工。
`MAX_STOP_BLOCKS = 3` 防止一个坏掉的测试套件把 agent 永远困住。

## 运行

```bash
python agents/s08_hooks.py
```

## 练习

1. 加一个 `PostToolUse` 钩子，运行你项目的代码格式化工具。
2. 写一个 `PreToolUse` 钩子，拦截 `git push` 到 `main`。
3. 新增一个 `SessionStart` 事件，把 `git log --oneline -5` 注入上下文。
