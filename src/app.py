"""CLI for baseline chatbot, Chroma FAQ chatbot and plan-and-execute Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from ai_levels.level2_llm_chatbot import build_rag_context, llm_chatbot
from ai_levels.level3_reactive_agent import AgentResult, PlanAndExecuteAgent
from knowledge_base import KnowledgeBaseError, get_knowledge_base
from prompts import CHATBOT_BASELINE_PROMPT
from providers import BaseLLMProvider, get_llm_provider
from tools import build_tool_registry


def load_test_cases(mode: str) -> list[dict[str, Any]]:
    filename = "test_cases_agent.json" if mode == "agent" else "test_cases.json"
    path = PROJECT_ROOT / "config" / filename
    with path.open("r", encoding="utf-8") as file:
        cases = json.load(file)
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"config/{filename} phải là danh sách không rỗng.")
    return cases


def print_agent_result(result: AgentResult, show_plan: bool, show_trace: bool) -> None:
    if show_plan:
        print("\n--- PLAN ---")
        print(json.dumps(result.plan, ensure_ascii=False, indent=2))
    if show_trace:
        print("\n--- TRACE ---")
        print(json.dumps(result.trace_as_dicts(), ensure_ascii=False, indent=2))
    print(f"Bot: {result.answer}")
    print(f"[status={result.status}; tool_calls={result.tool_calls}]")


def run_baseline_chat(provider: BaseLLMProvider) -> None:
    print("\nCHATBOT BASELINE - 1 LLM CALL, KHÔNG RAG, KHÔNG TOOL")
    print("Lệnh: exit")
    while True:
        try:
            question = input("\nBạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nĐã thoát baseline.")
            break
        if question.casefold() in {"exit", "quit", "thoát", "0"}:
            break
        if not question:
            print("Bot: Bạn hãy nhập một câu hỏi.")
            continue
        answer = provider.generate(question, system_prompt=CHATBOT_BASELINE_PROMPT)
        print(f"Bot: {answer}")


def run_agent_tests(provider: BaseLLMProvider, knowledge_base: Any) -> None:
    cases = load_test_cases("agent")
    requests_path = PROJECT_ROOT / "config" / "mock_after_sales_requests.json"
    requests_path.write_text(
        json.dumps({"data_version": "2026-07-28", "requests": []}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Đã reset mock_after_sales_requests.json để test deterministic.")
    print(f"\nĐã tải {len(cases)} Agent test case. Provider: {provider.model_name}")

    for case in cases:
        agent = PlanAndExecuteAgent(provider, knowledge_base)
        result = agent.run(case["question"], history=[])
        print("\n" + "=" * 80)
        print(f"CASE #{case['id']} | {case['category']}")
        print(f"Question : {case['question']}")
        print(f"Expected : {case['expected_behavior']}")
        print_agent_result(result, show_plan=True, show_trace=True)
        follow_ups = case.get("follow_ups", [])
        if isinstance(case.get("follow_up"), str):
            follow_ups = [case["follow_up"]]
        for follow_up in follow_ups:
            print(f"\nFollow-up: {follow_up}")
            result = agent.run(follow_up, history=[])
            print_agent_result(result, show_plan=False, show_trace=True)


def run_chatbot_tests(provider: BaseLLMProvider, knowledge_base: Any) -> None:
    cases = load_test_cases("chatbot")
    print(f"\nĐã tải {len(cases)} Chatbot test case. Provider: {provider.model_name}")
    for case in cases:
        answer = llm_chatbot(case["question"], provider, [], knowledge_base)
        print("\n" + "=" * 80)
        print(f"CASE #{case['id']} | {case['category']}")
        print(f"Question : {case['question']}")
        print(f"Expected : {case['expected_behavior']}")
        print(f"Answer   : {answer}")


def run_agent_chat(
    provider: BaseLLMProvider,
    knowledge_base: Any,
    show_plan: bool = False,
    show_trace: bool = False,
) -> None:
    history: list[dict[str, str]] = []
    agent = PlanAndExecuteAgent(provider, knowledge_base)
    plan_debug = show_plan
    trace_debug = show_trace

    print("\n" + "=" * 80)
    print("AI AGENT - PLANNER + 3 TOOL NGHIỆP VỤ")
    print("=" * 80)
    print("Planner luôn chạy. /plan on chỉ bật hiển thị plan để demo hoặc debug.")
    print("Tool chính: lookup_order | search_policy | build_return_options")
    print("Tool ghi tùy chọn: create_return_request, bắt buộc xác nhận.")
    print("Lệnh: /help | /tools | /plan on|off | /trace on|off | /clear | exit")

    while True:
        try:
            question = input("\nBạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nĐã thoát Agent.")
            break

        command = question.casefold()
        if command in {"exit", "quit", "thoát", "0", "/exit"}:
            print("Bot: Đã kết thúc phiên.")
            break
        if not question:
            print("Bot: Bạn hãy nhập yêu cầu.")
            continue
        if command == "/help":
            print(
                "Bot: Ví dụ: 'chính sách trả hàng thế nào?', 'tra cứu DH1024', "
                "'lập phương án trả hàng cho DH1024 vì mặc không vừa'. "
                "Sau khi Agent đưa phương án, nhập A/B/C rồi nhập 'xác nhận'."
            )
            continue
        if command == "/tools":
            print(build_tool_registry(knowledge_base).catalog_text())
            continue
        if command == "/clear":
            history.clear()
            agent.clear_pending()
            print("Bot: Đã xóa lịch sử và lựa chọn đang chờ.")
            continue
        if command in {"/plan on", "/plan off"}:
            plan_debug = command.endswith("on")
            print(f"Bot: Hiển thị plan = {plan_debug}")
            continue
        if command in {"/trace on", "/trace off"}:
            trace_debug = command.endswith("on")
            print(f"Bot: Hiển thị trace = {trace_debug}")
            continue

        result = agent.run(question, history)
        print_agent_result(result, plan_debug, trace_debug)
        history.extend(
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": result.answer},
            ]
        )
        history[:] = history[-10:]


def run_chatbot_chat(
    provider: BaseLLMProvider,
    knowledge_base: Any,
    show_context: bool = False,
) -> None:
    history: list[dict[str, str]] = []
    context_debug = show_context
    print("\nCHATBOT FAQ CHROMA RAG (READ-ONLY)")
    print("Lệnh: /context on | /context off | /clear | exit")
    while True:
        try:
            question = input("\nBạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nĐã thoát chatbot.")
            break
        command = question.casefold()
        if command in {"exit", "quit", "thoát", "0"}:
            break
        if command == "/clear":
            history.clear()
            continue
        if command in {"/context on", "/context off"}:
            context_debug = command.endswith("on")
            continue
        if context_debug:
            print(build_rag_context(question, history, knowledge_base))
        answer = llm_chatbot(question, provider, history, knowledge_base)
        print(f"Bot: {answer}")
        history.extend(
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ]
        )
        history[:] = history[-8:]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Order baseline, FAQ chatbot and AI agent.")
    parser.add_argument("--mode", choices=["baseline", "chatbot", "agent"], default="agent")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--provider", choices=["gemini", "mock"])
    parser.add_argument("--embedding-provider", choices=["gemini", "hash"])
    parser.add_argument("--show-context", action="store_true")
    parser.add_argument("--show-plan", action="store_true")
    parser.add_argument("--show-trace", action="store_true")
    parser.add_argument("--rebuild-index", action="store_true")
    parser.add_argument("--index-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        provider = get_llm_provider(args.provider)
    except ValueError as exc:
        print(f"LỖI KHỞI ĐỘNG: {exc}")
        raise SystemExit(1) from exc

    if args.mode == "baseline":
        print(f"LLM Provider: {provider.__class__.__name__} | Model: {provider.model_name}")
        run_baseline_chat(provider)
        return

    try:
        knowledge_base = get_knowledge_base(args.embedding_provider)
        index_info = knowledge_base.ensure_index(force=args.rebuild_index)
    except (KnowledgeBaseError, ValueError) as exc:
        print(f"LỖI KHỞI ĐỘNG: {exc}")
        raise SystemExit(1) from exc

    print(f"LLM Provider: {provider.__class__.__name__} | Model: {provider.model_name}")
    print(
        "Chroma: {document_count} chunks | embedding={embedding_backend} | "
        "rebuilt={rebuilt} | path={db_path}".format(**index_info)
    )
    if args.index_only:
        return
    if args.test:
        if args.mode == "agent":
            run_agent_tests(provider, knowledge_base)
        else:
            run_chatbot_tests(provider, knowledge_base)
        return
    if args.mode == "agent":
        run_agent_chat(
            provider,
            knowledge_base,
            show_plan=args.show_plan,
            show_trace=args.show_trace,
        )
    else:
        run_chatbot_chat(provider, knowledge_base, args.show_context)


if __name__ == "__main__":
    main()
