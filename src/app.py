"""Ứng dụng chatbot FAQ Chroma RAG, chưa sử dụng Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from ai_levels.level2_llm_chatbot import build_rag_context, llm_chatbot
from knowledge_base import KnowledgeBaseError, get_knowledge_base
from providers import BaseLLMProvider, get_llm_provider

load_dotenv()


def load_test_cases() -> list[dict[str, Any]]:
    path = PROJECT_ROOT / "config" / "test_cases.json"
    with path.open("r", encoding="utf-8") as file:
        cases = json.load(file)
    if not isinstance(cases, list) or not cases:
        raise ValueError("config/test_cases.json phải là danh sách không rỗng.")
    return cases


def run_test_suite(provider: BaseLLMProvider, knowledge_base: Any) -> None:
    cases = load_test_cases()
    print(f"\nĐã tải {len(cases)} test case. Provider: {provider.model_name}")
    print("Kiến trúc: Chroma retrieval + exact lookup + 1 LLM call + 0 agent loop")

    for case in cases:
        answer = llm_chatbot(
            case["question"], provider, history=[], knowledge_base=knowledge_base
        )
        print("\n" + "=" * 72)
        print(f"CASE #{case['id']} | {case['category']}")
        print(f"Question : {case['question']}")
        print(f"Expected : {case['expected_behavior']}")
        print(f"Answer   : {answer}")


def run_interactive_chat(
    provider: BaseLLMProvider,
    knowledge_base: Any,
    show_context: bool = False,
) -> None:
    history: list[dict[str, str]] = []
    context_debug = show_context

    print("\n" + "=" * 72)
    print("CHATBOT FAQ CHROMA RAG - ĐƠN HÀNG, TỒN KHO VÀ ĐỔI TRẢ")
    print("=" * 72)
    print("Chatbot chỉ tra cứu và giải thích, không tạo hoặc sửa dữ liệu.")
    print("Lệnh: /help | /test | /clear | /context on | /context off | exit")

    while True:
        try:
            question = input("\nBạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nĐã thoát chatbot.")
            break

        command = question.casefold()
        if command in {"exit", "quit", "thoát", "0", "/exit"}:
            print("Bot: Đã kết thúc phiên trò chuyện.")
            break
        if not question:
            print("Bot: Bạn hãy nhập câu hỏi.")
            continue
        if command == "/help":
            print(
                "Bot: Ví dụ: 'trả hàng như nào?', 'tôi mặc không vừa thì làm sao?', "
                "'size M còn bao nhiêu?', 'đơn DH1024 đổi size M được không?'"
            )
            continue
        if command == "/clear":
            history.clear()
            print("Bot: Đã xóa lịch sử hội thoại tạm thời.")
            continue
        if command == "/test":
            run_test_suite(provider, knowledge_base)
            continue
        if command == "/context on":
            context_debug = True
            print("Bot: Đã bật hiển thị context Chroma.")
            continue
        if command == "/context off":
            context_debug = False
            print("Bot: Đã tắt hiển thị context Chroma.")
            continue

        if context_debug:
            print("\n--- CHROMA CONTEXT DEBUG ---")
            print(build_rag_context(question, history, knowledge_base))
            print("--- END CONTEXT ---\n")

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
    parser = argparse.ArgumentParser(description="Chatbot FAQ dùng Chroma RAG.")
    parser.add_argument("--test", action="store_true", help="Chạy bộ test case.")
    parser.add_argument(
        "--provider", choices=["gemini", "mock"], help="Ghi đè LLM_PROVIDER."
    )
    parser.add_argument(
        "--embedding-provider",
        choices=["gemini", "hash"],
        help="Gemini cho semantic retrieval; hash chỉ để test offline.",
    )
    parser.add_argument(
        "--show-context", action="store_true", help="Hiển thị context Chroma."
    )
    parser.add_argument(
        "--rebuild-index", action="store_true", help="Xóa và tạo lại index Chroma."
    )
    parser.add_argument(
        "--index-only", action="store_true", help="Lập index xong rồi thoát."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        provider = get_llm_provider(args.provider)
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
        run_test_suite(provider, knowledge_base)
    else:
        run_interactive_chat(provider, knowledge_base, args.show_context)


if __name__ == "__main__":
    main()
