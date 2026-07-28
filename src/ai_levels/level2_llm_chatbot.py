"""Cấp độ 2: chatbot FAQ dùng Chroma RAG, chưa phải Agent."""

from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from knowledge_base import ChromaKnowledgeBase, KnowledgeBaseError, get_knowledge_base
from prompts import FAQ_CHATBOT_SYSTEM_PROMPT
from providers import BaseLLMProvider, get_llm_provider


def _history_text(history: list[dict[str, str]] | None) -> str:
    if not history:
        return "Chưa có lịch sử hội thoại."
    return "\n".join(
        f"{item.get('role', 'unknown')}: {item.get('content', '')}"
        for item in history[-6:]
    )


def build_rag_context(
    user_input: str,
    history: list[dict[str, str]] | None = None,
    knowledge_base: ChromaKnowledgeBase | None = None,
) -> str:
    """Truy xuất context bằng Chroma và exact lookup overlay."""
    kb = knowledge_base or get_knowledge_base()
    return kb.build_context(user_input, history)


# Alias để không làm hỏng import từ phiên bản trước.
build_mock_context = build_rag_context


def build_llm_prompt(
    user_input: str,
    context: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    return f"""
LỊCH SỬ HỘI THOẠI GẦN NHẤT:
{_history_text(history)}

NGỮ CẢNH RAG TRUY XUẤT TỪ CHROMA:
{context}

CÂU HỎI HIỆN TẠI:
{user_input.strip()}

Hãy trả lời trực tiếp câu hỏi hiện tại dựa trên các đoạn [KB]. Không nói rằng
bạn đã gọi tool hay thực hiện hành động, vì đây là chatbot RAG chỉ đọc dữ liệu.
""".strip()


def llm_chatbot(
    user_input: str,
    provider: BaseLLMProvider | None = None,
    history: list[dict[str, str]] | None = None,
    knowledge_base: ChromaKnowledgeBase | None = None,
) -> str:
    """Chroma retrieval rồi gọi LLM đúng một lần, không chạy ReAct loop."""
    if not isinstance(user_input, str) or not user_input.strip():
        return "Bạn hãy nhập một câu hỏi."

    try:
        context = build_rag_context(user_input, history, knowledge_base)
    except KnowledgeBaseError as exc:
        return f"LỖI KNOWLEDGE BASE: {exc}"
    except Exception as exc:
        return f"LỖI TRUY XUẤT RAG: {exc}"

    active_provider = provider or get_llm_provider()
    return active_provider.generate(
        build_llm_prompt(user_input, context, history),
        system_prompt=FAQ_CHATBOT_SYSTEM_PROMPT,
    )


def interactive_demo() -> None:
    provider = get_llm_provider()
    kb = get_knowledge_base()
    info = kb.ensure_index()
    history: list[dict[str, str]] = []
    print("=== CHATBOT FAQ CHROMA RAG ===")
    print(f"Knowledge base: {info['document_count']} chunks | {info['embedding_backend']}")
    print("Gõ exit để thoát.")

    while True:
        try:
            question = input("\nBạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nĐã thoát.")
            break
        if question.casefold() in {"exit", "quit", "thoát", "0"}:
            print("Bot: Đã kết thúc phiên trò chuyện.")
            break
        if not question:
            print("Bot: Bạn hãy nhập một câu hỏi.")
            continue

        answer = llm_chatbot(question, provider, history, kb)
        print(f"Bot: {answer}")
        history.extend(
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ]
        )
        history[:] = history[-8:]


if __name__ == "__main__":
    interactive_demo()
