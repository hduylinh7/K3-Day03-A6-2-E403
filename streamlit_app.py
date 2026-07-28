"""Streamlit chat UI for the order return AI Agent.

Run from the project root:
    python -m streamlit run streamlit_app.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
load_dotenv(PROJECT_ROOT / ".env")

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ai_levels.level3_reactive_agent import AgentResult, PlanAndExecuteAgent
from knowledge_base import KnowledgeBaseError, get_knowledge_base
from providers import get_llm_provider


st.set_page_config(
    page_title="Order Return AI Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .block-container {max-width: 1180px; padding-top: 1.4rem;}
        [data-testid="stChatMessage"] {border-radius: 14px;}
        .agent-subtitle {color: #7d8590; margin-top: -0.7rem; margin-bottom: 1rem;}
        .status-pill {
            display: inline-block;
            padding: 0.2rem 0.55rem;
            margin-right: 0.35rem;
            border: 1px solid rgba(125, 133, 144, 0.35);
            border-radius: 999px;
            font-size: 0.8rem;
        }
        .quick-help {
            border: 1px solid rgba(125, 133, 144, 0.25);
            border-radius: 14px;
            padding: 0.9rem 1rem;
            margin-bottom: 0.8rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner=False)
def build_runtime(
    provider_name: str,
    embedding_name: str,
    rebuild_nonce: int,
) -> tuple[Any, Any, dict[str, Any]]:
    """Initialize the provider and Chroma knowledge base once per configuration."""
    provider = get_llm_provider(provider_name)
    knowledge_base = get_knowledge_base(embedding_name)
    index_info = knowledge_base.ensure_index(force=rebuild_nonce > 0)
    return provider, knowledge_base, index_info


def initial_messages() -> list[dict[str, Any]]:
    return [
        {
            "role": "assistant",
            "content": (
                "Chào bạn! Tôi hỗ trợ **tra cứu đơn hàng**, **giải thích policy** và "
                "**lập phương án trả hàng**.\n\n"
                "Thử hỏi: `Tra cứu DH1024` hoặc "
                "`Lập phương án trả hàng cho DH1024 vì mặc không vừa`."
            ),
        }
    ]


def reset_conversation() -> None:
    st.session_state.messages = initial_messages()
    agent = st.session_state.get("agent")
    if agent is not None:
        agent.clear_pending()


def result_to_message(result: AgentResult) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": result.answer,
        "status": result.status,
        "tool_calls": result.tool_calls,
        "plan": result.plan,
        "trace": result.trace_as_dicts(),
    }


def conversation_history() -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in st.session_state.messages[-10:]:
        role = message.get("role")
        content = message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            history.append({"role": role, "content": content})
    return history


def run_agent_message(text: str, visible_text: str | None = None) -> None:
    display = visible_text or text
    st.session_state.messages.append({"role": "user", "content": display})
    try:
        with st.spinner("Agent đang lập kế hoạch và gọi công cụ..."):
            result = st.session_state.agent.run(text, history=conversation_history())
        st.session_state.messages.append(result_to_message(result))
    except Exception as exc:  # Final UI safety net
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": f"Giao diện gặp lỗi khi chạy Agent: `{exc}`",
                "status": "ui_error",
                "tool_calls": 0,
            }
        )


def render_debug(message: dict[str, Any], show_plan: bool, show_trace: bool) -> None:
    status = message.get("status")
    if status:
        st.markdown(
            f'<span class="status-pill">status: {status}</span>'
            f'<span class="status-pill">tool calls: {message.get("tool_calls", 0)}</span>',
            unsafe_allow_html=True,
        )

    plan = message.get("plan")
    if show_plan and isinstance(plan, dict) and plan:
        with st.expander("🧭 Execution plan", expanded=False):
            st.json(plan)

    trace = message.get("trace")
    if show_trace and isinstance(trace, list) and trace:
        with st.expander("🔎 Action / Observation trace", expanded=False):
            for event in trace:
                step = event.get("step", "?")
                tool = event.get("tool") or event.get("event", "event")
                st.markdown(f"**Step {step}: `{tool}`**")
                if event.get("reasoning_summary"):
                    st.caption(event["reasoning_summary"])
                if event.get("arguments") is not None:
                    st.markdown("Arguments")
                    st.json(event["arguments"])
                if event.get("observation") is not None:
                    st.markdown("Observation")
                    st.json(event["observation"])
                st.divider()


def render_pending_actions() -> None:
    agent: PlanAndExecuteAgent = st.session_state.agent

    if agent.pending_options is not None:
        options = agent.pending_options.options
        st.markdown("#### Chọn phương án")
        columns = st.columns(max(1, len(options)))
        for index, option in enumerate(options):
            option_id = str(option.get("option_id", index + 1))
            title = str(option.get("title", "Phương án"))
            description = str(option.get("description", ""))
            with columns[index]:
                st.markdown(f"**{option_id}. {title}**")
                st.caption(description)
                if st.button(
                    f"Chọn {option_id}",
                    key=f"choose_option_{option_id}",
                    use_container_width=True,
                ):
                    run_agent_message(option_id, visible_text=f"Chọn phương án {option_id}")
                    st.rerun()

    if agent.pending_create is not None:
        st.markdown("#### Xác nhận hành động")
        st.warning(
            "Đây là thao tác ghi dữ liệu mô phỏng. Chỉ xác nhận khi thông tin phương án đã đúng."
        )
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("✅ Xác nhận tạo yêu cầu", use_container_width=True):
                run_agent_message("xác nhận")
                st.rerun()
        with col_cancel:
            if st.button("Hủy", use_container_width=True):
                run_agent_message("hủy")
                st.rerun()


# Session defaults
if "messages" not in st.session_state:
    st.session_state.messages = initial_messages()
if "rebuild_nonce" not in st.session_state:
    st.session_state.rebuild_nonce = 0

provider_default = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
embedding_default = os.getenv("RAG_EMBEDDING_PROVIDER", "gemini").strip().lower()

with st.sidebar:
    st.header("⚙️ Cấu hình")
    provider_name = st.selectbox(
        "LLM provider",
        options=["gemini", "mock"],
        index=0 if provider_default == "gemini" else 1,
        help="Gemini dùng câu trả lời tự nhiên; Mock dùng fallback deterministic để demo offline.",
    )
    embedding_name = st.selectbox(
        "Embedding provider",
        options=["gemini", "hash"],
        index=0 if embedding_default == "gemini" else 1,
        help="Hash có thể dùng để test offline; Gemini phù hợp hơn cho truy xuất ngữ nghĩa.",
    )
    show_plan = st.checkbox("Hiển thị Planner", value=True)
    show_trace = st.checkbox("Hiển thị Trace", value=False)

    st.divider()
    if st.button("🧹 Xóa hội thoại", use_container_width=True):
        reset_conversation()
        st.rerun()
    if st.button("♻️ Xây lại Chroma index", use_container_width=True):
        st.session_state.rebuild_nonce += 1
        st.session_state.pop("runtime_key", None)
        st.session_state.pop("agent", None)
        st.rerun()

    st.divider()
    st.caption("Planner luôn hoạt động. Tùy chọn trên chỉ bật hoặc ẩn phần hiển thị.")

runtime_key = (provider_name, embedding_name, st.session_state.rebuild_nonce)

try:
    provider, knowledge_base, index_info = build_runtime(*runtime_key)
except (KnowledgeBaseError, ValueError, RuntimeError) as exc:
    st.error(f"Không khởi tạo được Agent: {exc}")
    st.info(
        "Kiểm tra file `.env`, cài dependencies, hoặc chọn `mock` + `hash` để chạy offline."
    )
    st.code("python -m pip install -r requirements.txt", language="bash")
    st.stop()

if st.session_state.get("runtime_key") != runtime_key or "agent" not in st.session_state:
    st.session_state.agent = PlanAndExecuteAgent(provider, knowledge_base)
    st.session_state.runtime_key = runtime_key
    reset_conversation()

st.title("🤖 Order Return AI Agent")
st.markdown(
    "<div class='agent-subtitle'>Planner nhẹ + tra cứu đơn + policy + phương án trả hàng</div>",
    unsafe_allow_html=True,
)

metric_1, metric_2, metric_3 = st.columns(3)
metric_1.metric("LLM", provider.model_name)
metric_2.metric("Chroma chunks", index_info.get("document_count", "?"))
metric_3.metric("Embedding", index_info.get("embedding_backend", embedding_name))

if len(st.session_state.messages) == 1:
    st.markdown("<div class='quick-help'><b>Câu hỏi gợi ý</b></div>", unsafe_allow_html=True)
    quick_prompts = [
        "Chính sách trả hàng trong bao lâu?",
        "Tra cứu đơn DH1024.",
        "Lập phương án trả hàng cho DH1024 vì áo mặc không vừa.",
    ]
    quick_columns = st.columns(3)
    for index, prompt in enumerate(quick_prompts):
        with quick_columns[index]:
            if st.button(prompt, key=f"quick_{index}", use_container_width=True):
                run_agent_message(prompt)
                st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            render_debug(message, show_plan=show_plan, show_trace=show_trace)

render_pending_actions()

prompt = st.chat_input("Nhập câu hỏi hoặc yêu cầu cho Agent...")
if prompt:
    run_agent_message(prompt)
    st.rerun()
