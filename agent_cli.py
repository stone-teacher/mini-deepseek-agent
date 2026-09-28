import logging
import argparse
import getpass
import os

from agent_runtime.context import ContextManager
from agent_runtime.llm import create_deepseek_llm
from agent_runtime.runtime import AgentRuntime
from agent_runtime.session import SessionStore


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="[%(levelname)s] %(message)s",
    )
    logging.getLogger("agent_runtime").setLevel(logging.INFO)

    parser = argparse.ArgumentParser(
        description="一个使用 DeepSeek 的最小 CLI Agent"
    )
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        api_key = getpass.getpass("DeepSeek API key: ").strip()
        if not api_key:
            print("没有输入 API key，程序退出。")
            return
        os.environ["DEEPSEEK_API_KEY"] = api_key

    store = SessionStore()
    runtime = AgentRuntime(
        llm=create_deepseek_llm(),
        context=ContextManager(),
    )
    session = store.get_or_create(
        args.user_id,
        args.session_id,
    )

    print("输入文字开始聊天。")
    print("/session 会话名：切换会话；/exit：退出。")
    print("会话保存在当前进程内，退出程序后不保留。")

    while True:
        try:
            user_text = input(
                f"\n[{session.user_id}/{session.session_id}] 你："
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            break

        if not user_text:
            continue

        if user_text == "/exit":
            print("已退出。")
            break

        command_parts = user_text.split(maxsplit=1)

        if command_parts[0] == "/session":
            if len(command_parts) != 2:
                print("用法：/session window-2")
                continue

            session = store.get_or_create(
                args.user_id,
                command_parts[1],
            )
            print(f"已切换到会话：{session.session_id}")
            continue

        try:
            answer = runtime.handle_user_input(
                session,
                user_text,
            )
        except Exception as exc:
            print(f"本轮执行失败，错误类型：{type(exc).__name__}")
            continue

        print(f"Agent：{answer}")


if __name__ == "__main__":
    main()