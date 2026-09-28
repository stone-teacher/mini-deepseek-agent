# Mini Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不使用 Agent 框架的前提下，完成一个使用 DeepSeek、支持工具调用、session 隔离、多轮对话和基础 context 压缩的最小 CLI Agent。

**Architecture:** `agent_cli.py` 负责 CLI 输入输出和依赖组装；`agent_runtime` 按 models、llm、tools、session、context、runtime 分层。runtime 只依赖 `LLMClient` 协议，真实 DeepSeek 和 Fake LLM 可以互换；第一版 session 只保存在进程内。

**Tech Stack:** Python 3.11+、OpenAI-compatible Chat Completions API、`openai` client、`pytest`、标准库 `dataclasses`/`json`/`argparse`，不使用 LangGraph、OpenHands 或 OpenClaw。

**Spec:** `docs/superpowers/specs/2026-09-22-mini-agent-design.md`

## Global Constraints

- 使用真实 DeepSeek API；默认 `DEEPSEEK_BASE_URL=https://api.deepseek.com`、`DEEPSEEK_MODEL=deepseek-chat`。
- API key 只从 `DEEPSEEK_API_KEY` 读取，不进入源码、日志、README、trace 或 Git。
- 默认测试不得访问网络；live 测试只有在 `RUN_LIVE_TESTS=1` 且设置 key 时运行。
- Agent Loop 默认 `max_steps=8`，工具异常转换为模型可理解的 `tool_error`，不能直接使 CLI 崩溃。
- 工具系统至少包含 `calculator`、mock `search`、session 内 `todo`。
- 用户亲自逐文件创建业务代码；Agent 只提供路径、职责、接口、小段任务、验收标准和排错建议。

---

### Task 1: 公共数据模型

**Files:**
- Create: `agent_runtime/__init__.py`
- Create: `agent_runtime/models.py`
- Test: 本任务不创建业务测试文件；使用 `python -m compileall agent_runtime` 做语法验收。

**Interfaces:**
- Produces `Message`、`ToolCall`、`ToolSpec`、`AssistantResponse`、`Todo`、`Session`，供所有后续模块导入。
- `Message.role` 只能表达 `system`、`user`、`assistant`、`tool`；`content` 可为空。
- `ToolCall` 暴露 `id`、`name`、`arguments: dict`。
- `AssistantResponse` 暴露 `content`、`tool_calls`、`reasoning_content`、`raw`。
- `Session` 暴露 `user_id`、`session_id`、`messages`、`todos`、`created_at`、`updated_at`。

- [ ] **Step 1: 用户创建目录和空包文件**

创建 `agent_runtime/`，在其中创建空的 `__init__.py`；不要创建其他源码文件。

- [ ] **Step 2: 用户输入最小 dataclass 定义**

只实现上述公共模型，使用类型注解和合理默认值；不添加序列化、数据库或额外业务方法。

- [ ] **Step 3: 运行语法验收**

运行：`python -m compileall agent_runtime`

预期：输出编译成功，退出码为 0。用户将实际输出贴回后再继续。

### Task 2: LLM 边界与 Fake LLM

**Files:**
- Create: `agent_runtime/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- `LLMClient.complete(*, messages: list[Message], tools: list[ToolSpec]) -> AssistantResponse`。
- `FakeLLM(responses: list[AssistantResponse])` 按顺序返回预设响应；耗尽时抛出明确异常。
- `DeepSeekLLMClient` 接收 base URL、model 和从环境读取的 key，但测试通过依赖注入的 fake client 验证映射，不访问网络。

- [ ] **Step 1: 用户先写 Fake LLM 测试**

测试第一次调用返回第一条预设响应，第二次调用返回第二条；第三次调用在预设耗尽时抛出明确异常。

- [ ] **Step 2: 运行测试确认失败**

运行：`pytest tests/test_llm.py -q`

预期：因 `agent_runtime.llm` 尚未存在而失败。

- [ ] **Step 3: 用户实现协议和 Fake LLM**

实现 `LLMClient` Protocol、`FakeLLM.complete` 以及最小异常类型；不要在这一任务实现 Loop。

- [ ] **Step 4: 运行测试确认通过**

运行：`pytest tests/test_llm.py -q`

预期：全部通过。

### Task 3: 工具协议、注册表和三个离线工具

**Files:**
- Create: `agent_runtime/tools.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- `ToolRegistry.register(spec)`、`get(name)`、`list_specs()`。
- `ToolSpec` 的 Schema 可转换为 OpenAI-compatible function tool 定义。
- calculator 只允许受限算术；search 使用固定 mock 数据；todo 读写传入的 `Session`。

- [ ] **Step 1: 写注册表和 Schema 测试**

断言注册、按名称获取、列出工具，以及每个工具 Schema 至少包含 `name`、`description`、`parameters`。

- [ ] **Step 2: 写工具行为和错误测试**

覆盖正常计算、search 命中/未命中、创建/列出/完成 todo，以及非法参数和 handler 异常转换为 `tool_error`。

- [ ] **Step 3: 运行失败测试**

运行：`pytest tests/test_tools.py -q`

预期：因工具实现尚未存在而失败。

- [ ] **Step 4: 用户实现最小工具系统**

先完成注册表和参数校验，再实现三个工具；不要引入网络搜索或任意代码执行。

- [ ] **Step 5: 运行工具测试**

运行：`pytest tests/test_tools.py -q`

预期：全部通过。

### Task 4: SessionStore 和 ContextManager

**Files:**
- Create: `agent_runtime/session.py`
- Create: `agent_runtime/context.py`
- Test: `tests/test_session_context.py`

**Interfaces:**
- `SessionStore.get_or_create(user_id, session_id) -> Session`。
- `ContextManager.build_messages(session, system_prompt, ...) -> list[Message]`。
- Context 未超预算时保留历史；超预算时保留 system、摘要、最近消息和所有未完成 todo，不放入完整 trace。

- [ ] **Step 1: 写 session 隔离和续聊测试**

断言不同 `(user_id, session_id)` 得到不同对象，同一二元组得到同一对象且消息/todo 状态保留。

- [ ] **Step 2: 写压缩测试**

使用很小字符预算触发压缩；断言 system prompt、最近消息和 pending todo 存在，早期消息被摘要，trace 未被全量注入。

- [ ] **Step 3: 运行失败测试**

运行：`pytest tests/test_session_context.py -q`

预期：因模块尚未存在而失败。

- [ ] **Step 4: 用户实现最小存储和压缩**

使用进程内字典；摘要可以是确定性的文本摘要，不调用 LLM，不引入向量数据库。

- [ ] **Step 5: 运行测试确认通过**

运行：`pytest tests/test_session_context.py -q`

预期：全部通过。

### Task 5: Agent Runtime Loop 和 trace

**Files:**
- Create: `agent_runtime/runtime.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- `AgentRuntime.handle_user_input(session, user_text) -> AgentResult`。
- `AgentResult` 至少包含最终文本和本轮 trace。
- runtime 接收 `LLMClient`、`ToolRegistry`、`ContextManager` 和 `max_steps`，不直接创建 DeepSeek client。

- [ ] **Step 1: 写直接回答和一次工具调用测试**

Fake LLM 第一轮返回工具调用、第二轮返回最终文本；断言 assistant/tool 消息顺序和最终答案。

- [ ] **Step 2: 补充异常和边界测试**

覆盖连续两次工具调用、错误工具名、非法参数、工具执行异常、FakeLLM 耗尽、达到 `max_steps`、工具 trace、带工具追问和纯对话追问。

- [ ] **Step 3: 运行失败测试**

运行：`pytest tests/test_runtime.py -q`

预期：因 runtime 尚未存在而失败。

- [ ] **Step 4: 用户实现最小 Loop**

严格按设计中的七步循环执行；每个工具错误写入 `role=tool` 消息后继续交给 LLM，不直接崩溃。

- [ ] **Step 5: 运行 runtime 测试**

运行：`pytest tests/test_runtime.py -q`

预期：全部通过。

### Task 6: CLI、配置和 README

**Files:**
- Create: `agent_cli.py`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `README.md`
- Test: `tests/test_cli.py`（只测试参数解析和可替换依赖，不访问网络）

**Interfaces:**
- CLI 命令：`python -m agent_cli --user-id alice --session-id window-1`。
- CLI 创建 session、注册工具、选择真实或 fake LLM，并循环读取用户输入。
- README 说明运行方式、系统设计、Loop、session 限制、memory 召回时机、测试命令和已知限制。

- [ ] **Step 1: 写参数解析测试**

断言缺少 user/session 参数时失败，提供两项参数时解析成功；退出命令不进入 runtime。

- [ ] **Step 2: 用户实现 CLI 和配置示例**

环境变量只读取 key/base URL/model；`.env.example` 不包含真实 secret。CLI 默认不打印完整 trace 或 key。

- [ ] **Step 3: 写 README 内容**

加入 AI Prompt 记录、问题解决过程、架构题五个模块各一道题及回答，并明确进程重启后 session 丢失。

- [ ] **Step 4: 运行 CLI 测试和帮助命令**

运行：`pytest tests/test_cli.py -q`；再运行：`python -m agent_cli --help`。

预期：测试通过，帮助文本包含两个必需参数。

### Task 7: 集成验收和可选 live test

**Files:**
- Modify: `tests/test_live.py`
- Modify: `README.md`（只补充实际验证结果）

- [ ] **Step 1: 运行完整离线测试**

运行：`pytest -q`

预期：默认不访问网络，全部通过。

- [ ] **Step 2: 检查敏感信息和工作区状态**

运行：`rg -n "sk-|DEEPSEEK_API_KEY=.*[^$]" .`；确认没有真实 key、完整敏感响应或本机绝对路径。

- [ ] **Step 3: 仅在用户显式配置时运行 live test**

只有 `RUN_LIVE_TESTS=1` 且 `DEEPSEEK_API_KEY` 已配置时执行；测试只发送最小请求，断言 response 结构，不断言固定自然语言全文。

- [ ] **Step 4: 记录验证结果**

把命令和结果摘要写入 README 的验证章节，不写入 key、请求头或完整响应。

