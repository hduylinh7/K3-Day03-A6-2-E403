"""Plan-and-execute agent with three main business tools.

Planner and tools are intentionally separate:
- DomainPlanner creates the execution plan.
- ToolRegistry executes business operations.
- The LLM only turns grounded observations into natural-language answers.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from knowledge_base import ChromaKnowledgeBase
from planner import DomainPlanner, ExecutionPlan
from prompts import AGENT_FINAL_SYSTEM_PROMPT
from providers import BaseLLMProvider
from tools import ToolRegistry, build_tool_registry


@dataclass
class TraceEvent:
    step: int
    event: str
    reasoning_summary: str = ""
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    observation: dict[str, Any] | None = None


@dataclass
class AgentResult:
    answer: str
    status: str
    plan: dict[str, Any]
    trace: list[TraceEvent] = field(default_factory=list)
    tool_calls: int = 0
    pending_selection: bool = False
    pending_confirmation: bool = False

    def trace_as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.trace]


@dataclass
class PendingOptions:
    original_query: str
    plan: dict[str, Any]
    order_id: str
    reason: str
    options: list[dict[str, Any]]
    trace: list[TraceEvent]


@dataclass
class PendingCreate:
    original_query: str
    plan: dict[str, Any]
    order_id: str
    reason: str
    option: dict[str, Any]
    trace: list[TraceEvent]


class PlanAndExecuteAgent:
    """Run a reliable domain plan and expose Action/Observation trace events."""

    def __init__(
        self,
        provider: BaseLLMProvider,
        knowledge_base: ChromaKnowledgeBase,
    ) -> None:
        self.provider = provider
        self.knowledge_base = knowledge_base
        self.planner = DomainPlanner()
        self.registry: ToolRegistry = build_tool_registry(knowledge_base)
        self.pending_options: PendingOptions | None = None
        self.pending_create: PendingCreate | None = None

    def clear_pending(self) -> None:
        self.pending_options = None
        self.pending_create = None

    @staticmethod
    def _explicit_confirmation(text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text.casefold()).strip()
        return normalized in {
            "xác nhận",
            "xac nhan",
            "tôi xác nhận",
            "toi xac nhan",
            "đồng ý",
            "dong y",
            "confirm",
            "yes",
            "ok tạo",
            "ok tao",
        }

    @staticmethod
    def _explicit_cancel(text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text.casefold()).strip()
        return normalized in {
            "hủy",
            "huy",
            "không",
            "khong",
            "không tạo",
            "khong tao",
            "không chọn",
            "khong chon",
            "cancel",
            "no",
        }

    @staticmethod
    def _format_vnd(value: Any) -> str:
        try:
            return f"{int(value):,}".replace(",", ".") + " đồng"
        except (TypeError, ValueError):
            return "không rõ"

    @staticmethod
    def _tool_call_count(trace: list[TraceEvent]) -> int:
        return sum(1 for event in trace if event.event == "tool_result")

    @staticmethod
    def _option_from_text(text: str, options: list[dict[str, Any]]) -> dict[str, Any] | None:
        normalized = re.sub(r"\s+", " ", text.casefold()).strip()
        compact = re.sub(r"[^a-z0-9à-ỹ]+", " ", normalized).strip()
        for option in options:
            option_id = str(option.get("option_id", "")).casefold()
            code = str(option.get("code", "")).casefold()
            title = str(option.get("title", "")).casefold()
            accepted = {
                option_id,
                f"chọn {option_id}",
                f"chon {option_id}",
                code,
                title,
            }
            if normalized in accepted or compact in accepted:
                return option
            if code and code in normalized:
                return option
            if title and title in normalized:
                return option
        return None

    def _execute_tool(
        self,
        trace: list[TraceEvent],
        step: int,
        summary: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        observation = self.registry.execute(tool_name, arguments)
        trace.append(
            TraceEvent(
                step=step,
                event="tool_result",
                reasoning_summary=summary,
                tool=tool_name,
                arguments=arguments,
                observation=observation,
            )
        )
        return observation

    def _final_prompt(
        self,
        question: str,
        plan: dict[str, Any],
        trace: list[TraceEvent],
    ) -> str:
        return f"""
NHIỆM VỤ: SOẠN CÂU TRẢ LỜI CUỐI

CÂU HỎI:
{question}

KẾ HOẠCH NGHIỆP VỤ:
{json.dumps(plan, ensure_ascii=False, indent=2)}

OBSERVATIONS TỪ TOOL:
{json.dumps([asdict(item) for item in trace], ensure_ascii=False, indent=2)}

Chỉ dùng dữ kiện trong Observation. Trả lời ngắn, rõ ràng, không nhắc tới
chain-of-thought. Không nói đã thực hiện hành động ghi dữ liệu nếu chưa có
Observation thành công từ create_return_request.
""".strip()

    def _fallback_policy_answer(self, observation: dict[str, Any]) -> str:
        if not observation.get("ok"):
            return observation.get("message", "Không tìm thấy policy phù hợp.")
        lines = ["Chính sách liên quan:"]
        for row in observation.get("results", [])[:5]:
            text = str(row.get("text", "")).replace("\n", " ").strip()
            lines.append(f"- {row.get('title')}: {text[:420]}")
        return "\n".join(lines)

    def _fallback_order_answer(self, observation: dict[str, Any]) -> str:
        if not observation.get("ok"):
            return observation.get("message", "Không tìm thấy đơn hàng.")
        order = observation.get("order", {})
        lines = [
            f"Đơn {order.get('order_id')} của khách {order.get('customer_id')} "
            f"({order.get('customer_display')}) hiện ở trạng thái {order.get('status_label')}.",
            f"Ngày đặt: {order.get('ordered_at')}; ngày giao: {order.get('delivered_at') or 'chưa giao'}; "
            f"thanh toán: {order.get('payment_method')}; tổng: {self._format_vnd(order.get('total_vnd'))}.",
            "Sản phẩm:",
        ]
        for item in order.get("items", []):
            lines.append(
                f"- {item.get('quantity')} x {item.get('product_name')} "
                f"({item.get('variant')}, SKU {item.get('sku')})"
            )
        if order.get("active_return_requests"):
            lines.append("Đơn đang có yêu cầu hậu mãi hoạt động.")
        return "\n".join(lines)

    def _compose_grounded_answer(
        self,
        question: str,
        plan: dict[str, Any],
        trace: list[TraceEvent],
        fallback: str,
    ) -> str:
        if str(getattr(self.provider, "model_name", "")).startswith("offline-"):
            return fallback
        answer = self.provider.generate(
            self._final_prompt(question, plan, trace),
            system_prompt=AGENT_FINAL_SYSTEM_PROMPT,
        )
        if not answer.strip() or answer.startswith("[Gemini Error]"):
            return fallback
        return answer.strip()

    def _format_options(self, observation: dict[str, Any]) -> str:
        lines = [
            f"Đã xây dựng phương án cho đơn {observation.get('order_id')} "
            f"(khách {observation.get('customer_id')}).",
        ]
        blockers = observation.get("blockers", [])
        warnings = observation.get("warnings", [])
        if blockers:
            lines.append("\nĐiểm chặn:")
            lines.extend(f"- {item}" for item in blockers)
        if warnings:
            lines.append("\nLưu ý:")
            lines.extend(f"- {item}" for item in warnings)

        lines.append("\nCác phương án để quản lý lựa chọn:")
        for option in observation.get("options", []):
            recommended = " [Đề xuất]" if option.get("recommended") else ""
            lines.append(
                f"{option.get('option_id')}. {option.get('title')}{recommended}\n"
                f"   {option.get('description')}"
            )
        lines.append("\nNhập A, B hoặc C để chọn phương án. Chưa có dữ liệu nào bị thay đổi.")
        return "\n".join(lines)

    def _handle_pending(self, user_input: str) -> AgentResult | None:
        if self.pending_create is not None:
            pending = self.pending_create
            if self._explicit_cancel(user_input):
                self.clear_pending()
                return AgentResult(
                    answer="Đã hủy thao tác. Không có dữ liệu nào bị thay đổi.",
                    status="cancelled",
                    plan=pending.plan,
                    trace=pending.trace,
                    tool_calls=self._tool_call_count(pending.trace),
                )
            if self._explicit_confirmation(user_input):
                arguments = {
                    "order_id": pending.order_id,
                    "option_code": pending.option.get("code"),
                    "request_type": pending.option.get("request_type"),
                    "reason": pending.reason,
                    "confirmed": True,
                }
                trace = list(pending.trace)
                observation = self._execute_tool(
                    trace,
                    len(trace) + 1,
                    "Người quản lý đã xác nhận phương án đã chọn.",
                    "create_return_request",
                    arguments,
                )
                self.clear_pending()
                if observation.get("ok"):
                    request = observation.get("request", {})
                    answer = (
                        f"Đã tạo yêu cầu {request.get('request_id')} cho đơn {request.get('order_id')} "
                        f"ở trạng thái {request.get('status_label')}. Yêu cầu chưa đồng nghĩa với "
                        "đã hoàn tiền hoặc chấp thuận trả hàng."
                    )
                    status = "completed"
                else:
                    answer = observation.get("message", "Không thể tạo yêu cầu.")
                    status = "tool_error"
                return AgentResult(
                    answer=answer,
                    status=status,
                    plan=pending.plan,
                    trace=trace,
                    tool_calls=self._tool_call_count(trace),
                )
            # A new unrelated request should not be trapped behind confirmation.
            self.clear_pending()
            return None

        if self.pending_options is not None:
            pending = self.pending_options
            if self._explicit_cancel(user_input):
                self.clear_pending()
                return AgentResult(
                    answer="Đã hủy việc chọn phương án. Không có dữ liệu nào bị thay đổi.",
                    status="cancelled",
                    plan=pending.plan,
                    trace=pending.trace,
                    tool_calls=self._tool_call_count(pending.trace),
                )
            selected = self._option_from_text(user_input, pending.options)
            if selected is not None:
                self.pending_create = PendingCreate(
                    original_query=pending.original_query,
                    plan=pending.plan,
                    order_id=pending.order_id,
                    reason=pending.reason,
                    option=selected,
                    trace=list(pending.trace),
                )
                self.pending_options = None
                return AgentResult(
                    answer=(
                        f"Bạn đã chọn {selected.get('option_id')}: {selected.get('title')}. "
                        f"Xác nhận tạo yêu cầu mô phỏng cho đơn {pending.order_id}? "
                        "Nhập 'xác nhận' để tiếp tục hoặc 'hủy' để dừng."
                    ),
                    status="awaiting_confirmation",
                    plan=pending.plan,
                    trace=pending.trace,
                    tool_calls=self._tool_call_count(pending.trace),
                    pending_confirmation=True,
                )
            self.clear_pending()
            return None

        return None

    def run(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> AgentResult:
        del history
        if not isinstance(user_input, str) or not user_input.strip():
            return AgentResult("Bạn hãy nhập một yêu cầu.", "invalid_input", {})

        pending_result = self._handle_pending(user_input.strip())
        if pending_result is not None:
            return pending_result

        question = user_input.strip()
        execution_plan: ExecutionPlan = self.planner.create_plan(question)
        plan = execution_plan.as_dict()
        trace: list[TraceEvent] = []

        if "order_id" in execution_plan.missing_information:
            return AgentResult(
                answer=(
                    "Bạn hãy cung cấp mã đơn cần xử lý, ví dụ DH1024. "
                    "Agent không tự chọn ngẫu nhiên đơn của khách hàng."
                ),
                status="needs_input",
                plan=plan,
                trace=trace,
            )

        if execution_plan.intent == "unsupported":
            return AgentResult(
                answer=(
                    "Hãy yêu cầu một trong ba việc: tra cứu đơn theo mã DH, hỏi chính sách, "
                    "hoặc lập phương án trả hàng cho một đơn cụ thể."
                ),
                status="needs_input",
                plan=plan,
                trace=trace,
            )

        observations: dict[str, dict[str, Any]] = {}
        for step in execution_plan.steps:
            tool_name = step.suggested_tool
            if tool_name is None:
                continue

            if tool_name == "lookup_order":
                arguments = {"order_id": execution_plan.order_id}
            elif tool_name == "search_policy":
                query = (
                    f"trả hàng với lý do {execution_plan.reason}"
                    if execution_plan.intent == "return_options"
                    else question
                )
                arguments = {"query": query, "top_k": 5}
            elif tool_name == "build_return_options":
                arguments = {
                    "order_id": execution_plan.order_id,
                    "reason": execution_plan.reason,
                }
            else:
                return AgentResult(
                    answer=f"Planner tạo tool không hợp lệ: {tool_name}",
                    status="planner_error",
                    plan=plan,
                    trace=trace,
                    tool_calls=self._tool_call_count(trace),
                )

            observation = self._execute_tool(
                trace,
                step.id,
                step.description,
                tool_name,
                arguments,
            )
            observations[tool_name] = observation

            if not observation.get("ok"):
                return AgentResult(
                    answer=observation.get("message", f"Tool {tool_name} thất bại."),
                    status="tool_error",
                    plan=plan,
                    trace=trace,
                    tool_calls=self._tool_call_count(trace),
                )

        if execution_plan.intent == "policy_question":
            observation = observations["search_policy"]
            fallback = self._fallback_policy_answer(observation)
            answer = self._compose_grounded_answer(question, plan, trace, fallback)
            return AgentResult(
                answer,
                "completed",
                plan,
                trace,
                self._tool_call_count(trace),
            )

        if execution_plan.intent == "order_lookup":
            observation = observations["lookup_order"]
            fallback = self._fallback_order_answer(observation)
            answer = self._compose_grounded_answer(question, plan, trace, fallback)
            return AgentResult(
                answer,
                "completed",
                plan,
                trace,
                self._tool_call_count(trace),
            )

        if execution_plan.intent == "return_options":
            observation = observations["build_return_options"]
            options = observation.get("options", [])
            self.pending_options = PendingOptions(
                original_query=question,
                plan=plan,
                order_id=str(execution_plan.order_id),
                reason=execution_plan.reason,
                options=options,
                trace=list(trace),
            )
            return AgentResult(
                answer=self._format_options(observation),
                status="awaiting_selection",
                plan=plan,
                trace=trace,
                tool_calls=self._tool_call_count(trace),
                pending_selection=True,
            )

        return AgentResult(
            answer="Không xác định được kết quả cần trả.",
            status="internal_error",
            plan=plan,
            trace=trace,
            tool_calls=self._tool_call_count(trace),
        )
