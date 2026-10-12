# s02 · 工具

> 代码：[`agents/s02_tools.py`](../../agents/s02_tools.py) · [← s01](s01-agent-loop.md) · 下一章：[s03 权限 →](s03-permissions.md)

## 问题

只有 `bash` 时，模型改文件靠 `sed -i 's/.../.../'`，读文件靠 `cat`。
结果就是转义 bug、5 MB 的输出，以及一不小心写到项目外面去的文件。

## 思路

维护一张表：**工具名** → **给模型看的 schema** + **真正执行的 Python 函数**。
循环本身一行不改，只是变成去表里查函数。

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

那个 `except` 是本章最重要的一行：**工具出错是结果，不是崩溃。**
"文件不存在"会被送回给模型，它接着跑一下 `glob`，就找到了正确的路径。
Agent 看起来聪明，很大程度上是因为它能从自己的错误里恢复，而前提是它得**看得到**这些错误。

## 值得抄的设计

**`edit_file` 替换一段精确且唯一的文本。**

```python
count = text.count(old)
if count != 1:
    return f"Error: `old` must appear exactly once in {path}, found {count} times. Add more context."
```

不用行号（一改就错位），也不用正则（转义地狱）。如果匹配到多处，就让模型多带点上下文，
效果出奇地好。Claude Code 的 `Edit` 工具也是这么做的。

**`read_file` 带行号、按窗口返回。** 大文件每次给 400 行，并提示下一段从哪读。
模型永远不会收到一个它没要过的 2 MB 文件。

**`safe_path` 让所有文件工具都待在工作区里。**

```python
def safe_path(p):
    root = Path.cwd().resolve()
    path = (root / p).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"path escapes the workspace: {p}")
    return path
```

`../../etc/passwd` 和 `/tmp/x` 都会被拒绝。（`bash` 依然什么都能干，s03 会处理这个问题。）

**描述就是提示词。** "改文件前先读一遍"、"优先用 `grep` 工具而不是 `bash grep`"，
这些写在系统提示词和工具描述里。工具描述是整个上下文里被模型读得最多的文字之一，写它要像写代码一样认真。

## 运行

```bash
python agents/s02_tools.py
```

演示会写一个 `fizzbuzz.py`，运行它，改一个字符串，再用 `grep` 验证。每一步都是真实的工具调用。

## 练习

1. 加一个 `list_dir` 工具。需要改两处：`TOOLS` 和 `HANDLERS`。
2. 让 `edit_file` 支持 `replace_all: true`。
3. 让 `read_file` 遇到二进制文件时给出友好的提示，而不是返回乱码。
