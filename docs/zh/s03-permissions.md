# s03 · 权限

> 代码：[`agents/s03_permissions.py`](../../agents/s03_permissions.py) · [← s02](s02-tools.md) · 下一章：[s04 待办清单 →](s04-todo.md)

## 问题

模型可以执行任意 shell 命令。而模型会看错指令，会听从刚读到的 README 里被注入的文字，
偶尔还会觉得 `rm -rf build/ ~/old` 是在"清理"。在系统提示词里写一句"请小心"，算不上安全边界。

## 思路

harness 在**每一次**工具调用执行之前，按固定顺序检查：

```
1. 拒绝规则    sudo、rm -rf /、curl | sh、mkfs、fork 炸弹     -> 一律拒绝
2. 只读工具？  read_file、glob、grep                         -> 一律放行
3. 模式        auto：全部放行 / plan：拒绝一切写操作
4. 问人        y / n / a(总是允许) / 或者直接输入反馈
```

```python
def check_permission(name, args):
    """None = 放行。字符串 = 拒绝理由（会发给模型）。"""
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

## "拒绝"也是反馈

关键一步：拒绝**不是异常**，而是作为工具结果返回：

```
⏺ write_file(path="hello.md", ...)
  allow write_file? [y/n/a/feedback] 放到 docs/ 下面
  │ Denied by the user, who says: 放到 docs/ 下面
⏺ write_file(path="docs/hello.md", ...)
```

模型读到理由，自己调整。没有这一步，权限确认只是个开关；有了它，
权限确认就成了你在 agent 干活时随时"掌舵"的方式。

## 三种模式

| `HARNESS_PERMISSION` | 行为 | 适用场景 |
|---|---|---|
| `ask`（默认） | 读随便读，写和执行前先问 | 日常使用 |
| `auto` | 除拒绝规则外全部放行 | 沙箱、CI、用完即弃的虚拟机 |
| `plan` | 只读，所有写操作都被拒绝 | "先看看情况，给我个方案" |

plan 模式只花了一行代码，却是真实 harness 里最有用的功能之一：在动任何东西之前，先拿到调查结果和方案。

## 它*防不住*什么

拒绝规则是正则表达式，而 `bash` 是图灵完备的。`s"u"do`、`python -c "import shutil; ..."`、
或者模型先写一个脚本再执行它，都能绕过任何模式列表。所以拒绝规则只用来防**意外**。
面对有恶意的模型，真正的边界是沙箱：容器、虚拟机或操作系统级别的隔离。生产级 harness 会把这些层层叠加。

## 运行

```bash
python agents/s03_permissions.py                         # 演示：sudo 被拦，写文件被用户改道
HARNESS_PERMISSION=plan python agents/s03_permissions.py # 配上真实 Key，试着让它改点东西
```

## 练习

1. 加一个白名单：`git status`、`git diff`、`ls`、`pytest` 不用询问直接执行。
2. 把"总是允许"按**命令前缀**（如 `npm test`）记住，而不是按工具。
3. 批准 `edit_file` 之前先展示 diff 预览。
