# Mini Agent 设计草案

日期：2026-09-22  
状态：待用户审阅  
范围：第一版 CLI Agent；只定义设计，不包含业务源码实现。

## 1. 目标与非目标

第一版实现一个从零编写的最小 Agent，使用真实 DeepSeek OpenAI-compatible Chat Completions API，支持工具调用、多轮对话、session 隔离、基础 context 压缩、异常处理和可检查的工具执行 trace。

主流程不使用 LangGraph、OpenHands、OpenClaw 或其他 Agent 框架。工具注册、工具 Schema、模型响应解析、Agent Loop 和 session 管理由本项目自行实现。

非目标：持久化数据库、并发 session、Web UI、复杂向量记忆、自动规划器、隐藏 reasoning 的长期保存、默认联网测试，以及完整生产级安全沙箱。

## 2. 方案选择

采用小型分层项目：模型数据结构、LLM 边界、工具系统、运行时循环、session 存储和 context 管理分别放在独立模块。CLI 只负责参数读取、输入输出和依赖组装。

相比单文件脚本，这个方案增加少量文件，但能让 Fake LLM 替代真实 API，直接测试 Loop 和工具行为；相比引入 Agent 框架，它保留了本项目要求观察的公共接口和数据流。

第一版 session 使用进程内字典：`sessions[(user_id, session_id)] -> Session`。同一键在一次进程生命周期内继续消息和 todo；进程重启后丢失，这是 README 中明确记录的已知限制。

## 3. 目录与职责

```text
mini-agent/
├─ agent_runtime/
│  ├─ models.py       # Message、ToolCall、ToolSpec、AssistantResponse、Session
│  ├─ llm.py          # LLMClient、DeepSeekLLMClient、FakeLLM
│  ├─ tools.py        # 工具协议、注册表、calculator/search/todo
│  ├─ runtime.py      # 一次输入的 Agent Loop 和 trace
│  ├─ session.py      # SessionStore
│  └─ context.py      # 历史消息筛选、摘要和 todo 保留
├─ agent_cli.py       # CLI 入口
├─ tests/             # 不依赖网络的单元测试和显式启用的 live 测试
├─ README.md
├─ requirements.txt
└─ .env.example
```

依赖方向固定为：`agent_cli -> runtime -> (llm, tools, context, session) -> models`。`runtime` 只依赖 `LLMClient` 协议，不直接依赖 DeepSeek SDK；工具实现不依赖 CLI。

## 4. 核心数据模型

`Message` 表示发送给模型或保存到 session 的一条消息：`role` 为 `system | user | assistant | tool`，并包含 `content: str | None`、可选 `tool_calls`、`tool_call_id`、`name` 和 `created_at`。

`ToolCall` 包含 `id`、`name` 和已经解析为字典的 `arguments`。`ToolSpec` 包含工具名、描述、JSON Schema 参数和 callable handler。`AssistantResponse` 包含 `content`、`tool_calls`、可选 `reasoning_content` 和原始响应字典 `raw`。

`Session` 包含 `user_id`、`session_id`、`messages`、`todos`、`created_at`、`updated_at`。todo 的最小状态至少需要标识、文本和 `pending/done` 状态，以便 context 压缩时保留未完成事项。

## 5. LLMClient 与 DeepSeek 映射

公共边界：

```python
class LLMClient(Protocol):
    def complete(
        self,
        *,
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> AssistantResponse: ...
```

`DeepSeekLLMClient` 使用 OpenAI-compatible client：

- API key 从 `DEEPSEEK_API_KEY` 读取，不写入代码、日志、README 或 trace。
- `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`。
- `DEEPSEEK_MODEL` 默认 `deepseek-chat`。
- 内部 `Message` 转换成 Chat Completions 的 `messages` 数组。
- `ToolSpec` 转换成 `{"type": "function", "function": {"name", "description", "parameters"}}`。
- 调用 `client.chat.completions.create(model=..., messages=..., tools=...)`。
- 只解析第一条 choice：读取 `message.content`、可选 `message.reasoning_content` 和 `message.tool_calls`。
- 每个函数参数从 `tool_call.function.arguments` 经 `json.loads` 转成字典。

参数 JSON 无法解析、模型响应结构缺失或 API 调用失败时，客户端返回可诊断异常给 runtime；不把 key 或完整请求中的敏感信息写入错误信息。

`FakeLLM` 接受预设 `AssistantResponse` 序列，按调用顺序返回，用于确定性测试；序列耗尽时抛出明确异常，帮助测试发现 Loop 次数或预设不足。

## 6. 工具系统

`ToolRegistry` 只提供 `register(spec)`、`get(name)` 和 `list_specs()`。模型看到的工具描述由 `list_specs()` 生成；runtime 执行时再次按名称查找 handler，保持模型 Schema 与执行入口一致。

第一版至少提供三个工具：

1. `calculator`：执行受限的算术表达式，不允许任意 Python 执行。
2. `search`：使用固定 mock 数据按关键词返回结果，保证离线可测。
3. `todo`：创建、列出和完成 session 内 todo，并返回更新后的状态。

参数校验在执行 handler 前完成。未知工具、缺失字段、字段类型不符或 handler 抛出异常，都转换为结构化的短结果，例如 `tool_error: ValueError: ...`，写入 `role=tool` 消息，再让模型决定解释或重试。

## 7. Agent Loop 与 trace

一次 `handle_user_input` 最多执行 `max_steps`，默认 8：追加 user message；由 `ContextManager` 生成发送给 LLM 的消息；调用并解析 `LLMClient`；无 tool call 时保存 assistant message 并返回；有 tool call 时保存 assistant tool-call message，逐个校验、查找和执行工具，保存 tool message 后继续循环；超过上限则返回达到工具调用上限的可解释结果。

每次工具执行记录 trace 项，至少包含 step、tool_call_id、工具名、脱敏后的参数摘要、成功/失败、结果摘要和耗时。默认不把完整 trace 放进后续 context；trace 用于 CLI 调试输出和测试断言。

## 8. Context 与 memory 召回时机

`ContextManager` 采用确定性的基础压缩：始终保留 system prompt；未超过预算时保留完整历史；超过字符数或估算 token 预算时把较早消息压缩成一条摘要并保留最近 N 轮；始终把未完成 todo 的文本和状态放入 context；只保留对后续推理有用的工具结果；`reasoning_content` 只进入 trace，不作为长期 conversation context 的必要内容。

memory 的召回时机是“构造下一次 LLM 请求的 context 时”，而不是每次工具执行后单独调用。第一版没有独立向量 memory；可召回内容就是当前 session 的摘要、最近消息和未完成 todo。这样避免引入未验证的检索系统，同时保留未来增加持久 memory 的插入点。

## 9. Session 隔离与多轮对话

CLI 要求 `--user-id` 和 `--session-id`。`SessionStore.get_or_create(user_id, session_id)` 以二元组作为唯一键：`(alice, window-1)` 与 `(alice, window-2)` 使用不同 Session；相同二元组再次进入时复用消息、摘要和 todo；不同用户即使 session_id 相同也互相隔离。

一次 CLI 进程内支持连续输入，空行不作为用户消息；退出命令由 CLI 处理，不进入 Agent Loop。

## 10. 错误边界

LLM 层处理配置缺失、网络/API 错误和响应解析错误；工具层处理未知工具、参数错误和 handler 异常并转成 `tool_error` 工具消息；Loop 层处理 `max_steps`、FakeLLM 耗尽或不可恢复异常，返回用户可理解的结果并记录 trace。API key 只从环境读取，日志和测试断言只能使用模型名、provider 域名、错误类型和脱敏摘要。

## 11. 测试策略与验收矩阵

默认 `pytest` 只运行 Fake LLM 和 mock 工具测试，不访问网络。覆盖：直接回答、一次工具调用后回答、连续两次工具调用、错误工具名、非法工具参数、工具执行异常、达到最大 loop 次数、同用户不同 session 隔离、同 session 继续对话、context 压缩和未完成 todo 保留、工具 trace、带工具的追问、纯对话追问。

真实 API 集成测试必须同时满足 `RUN_LIVE_TESTS=1` 和 `DEEPSEEK_API_KEY` 已配置，否则跳过。live 测试只做最小请求，不断言易变的自然语言全文，不打印 key。

第一阶段文件验收：创建 `agent_runtime/models.py` 后运行 `python -m compileall agent_runtime`，再由用户提供实际输出；后续每次只推进一个小文件或一个小实验。

## 12. CLI、配置与 README 要求

入口命令：

```text
python -m agent_cli --user-id alice --session-id window-1
```

`.env.example` 只列变量名和无敏感示例值。README 必须说明运行方式、系统设计、工具注册和 Loop、session 限制、context/memory 召回时机与放置方式、测试命令、live 测试开关和已知限制。

README 还要附 AI Prompt 记录、问题解决过程、架构题五个模块各一道题及回答。任何真实 secret、完整 API 响应中的敏感字段和本机路径都不能提交。

## 13. 后续实施顺序

1. `agent_runtime/models.py`：只定义公共数据模型；验收 `compileall`。
2. `agent_runtime/llm.py`：先完成 Fake LLM，再写 DeepSeek 映射；用脱敏 fake response 做解析测试。
3. `agent_runtime/tools.py`：协议、注册表和三个离线工具；测试 Schema、校验和异常转换。
4. `agent_runtime/session.py` 与 `context.py`：隔离、续聊和压缩测试。
5. `agent_runtime/runtime.py`：实现 Loop 和 trace；完成主要测试矩阵。
6. `agent_cli.py`、README、`.env.example`、`requirements.txt`。
7. 显式配置后再执行 live test；不把 live test 当作默认验收。

