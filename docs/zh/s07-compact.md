# s07 · 上下文压缩：有计划地遗忘

> 代码：[`agents/s07_compact.py`](../../agents/s07_compact.py) · [← s06](s06-skills.md) · 下一章：[s08 钩子 →](s08-hooks.md)

## 问题

`messages` 里的东西永远不会离开。读过十个文件，之后每一轮都要把这十个文件重新发一遍。
长会话会变慢、变贵，最后撞上上下文窗口上限，直接卡死。

## 两层遗忘

**第一层：微压缩（上下文 > 预算的 50%）。**
把旧的、大块的工具输出替换成一行占位符，最新的几条结果保持原样。

```python
def micro_compact(messages):
    for m in [m for m in messages if m["role"] == "tool"][:-KEEP_RECENT]:
        if len(m["content"]) > 500 and not m["content"].startswith("[cleared"):
            m["content"] = f"[cleared: old {m['name']} output ({len(m['content'])} chars). Run the tool again if needed.]"
```

这么做是安全的，因为工具输出**可以重新生成**：模型需要那个文件，再读一次就行，占位符里也是这么告诉它的。

**第二层：完整压缩（上下文 > 预算，或模型主动要求）。**
把完整对话记录存盘，让模型写一份摘要，然后从摘要重新开始（简化版）：

```python
def full_compact(messages):
    path = save_transcript(messages)                      # .harness/transcripts/*.jsonl
    summary = llm.chat(SUMMARY_PROMPT, [{"role": "user", "content": transcript}])["content"]
    messages[:] = [{"role": "user", "content":
        f"[compacted - full transcript saved at {path}]\n\nSummary of the session so far:\n{summary}\n\n"
        f"The user's latest request was:\n{last_request}\n\nContinue from here."}]
```

摘要提示词要求写出接着干活所需的一切：目标、已做的决定、**准确的文件路径**、
有效的命令、遇到的错误和解决办法、未完成的待办、下一步。一句"我们改了一些文件"的摘要毫无用处。

模型也可以通过 `compact` 工具主动触发压缩，比如在两个不相关的任务之间。

## 缓存的取舍

s04 主张"历史只追加"，压缩则是有意打破这条规则。修改旧消息会让服务商的提示词缓存从那个位置开始失效，
下一次请求要为之后的所有内容付全价。

所以压缩**只在越过阈值时才做**，而且一次性批量做完。每轮清理一点点，等于每轮都让缓存失效，两头吃亏。
这是一个真实的工程取舍，生产级 harness 会仔细调这个参数。

## 计量

`estimate_tokens` 按大约 4 个字符算 1 个 token。很粗糙，但 harness 只需要知道自己在阈值的哪一边。
真实的 harness 会读取每次 API 响应里返回的精确 `usage` 数据。

## 运行

```bash
python agents/s07_compact.py
HARNESS_COMPACT_AT=20000 python agents/s07_compact.py   # 小预算，配合真实模型
```

演示里，模型分三段读完一个 1200 行的日志（故意浪费），于是微压缩清掉了最早那次读取；
接着模型调用 `compact`，整段对话被压成一份摘要。

## 练习

1. 用 API 响应里真实的 `usage` 字段替代估算。
2. 完整压缩后，除了摘要，再原样保留最近 *N* 条消息。
3. 加一个 `/transcript` 命令在旧记录里搜索，让信息不会真正丢失。
