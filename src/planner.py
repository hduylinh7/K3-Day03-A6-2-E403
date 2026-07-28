"""Reliable domain planner for the order return agent.

The planner is intentionally deterministic. It produces a short visible plan
from the user's intent, so planning cannot fail because an LLM returned
truncated JSON. The LLM is still used to write natural-language answers after
business tools have returned observations.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

ORDER_ID_PATTERN = re.compile(r"\bDH\d{3,}\b", re.IGNORECASE)


@dataclass(frozen=True)
class PlanStep:
    id: int
    description: str
    suggested_tool: str | None
    depends_on: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionPlan:
    goal: str
    intent: str
    steps: list[PlanStep]
    requires_confirmation: bool = False
    missing_information: list[str] = field(default_factory=list)
    order_id: str | None = None
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "intent": self.intent,
            "steps": [asdict(step) for step in self.steps],
            "requires_confirmation": self.requires_confirmation,
            "missing_information": list(self.missing_information),
            "order_id": self.order_id,
            "reason": self.reason,
            "planner_type": "deterministic_domain_planner",
        }


class DomainPlanner:
    """Convert one user request into a compact executable business plan."""

    POLICY_HINTS = (
        "chính sách",
        "chinh sach",
        "policy",
        "đổi trả",
        "doi tra",
        "hoàn tiền",
        "hoan tien",
        "bao lâu",
        "bao lau",
        "mấy ngày",
        "may ngay",
        "điều kiện",
        "dieu kien",
    )
    RETURN_HINTS = (
        "trả hàng",
        "tra hang",
        "hoàn hàng",
        "hoan hang",
        "gửi lại",
        "gui lai",
        "return",
    )
    PLAN_HINTS = (
        "kế hoạch",
        "ke hoach",
        "phương án",
        "phuong an",
        "đề xuất",
        "de xuat",
        "lập plan",
        "lap plan",
        "xử lý trả",
        "xu ly tra",
    )
    LOOKUP_HINTS = (
        "tra cứu",
        "tra cuu",
        "kiểm tra đơn",
        "kiem tra don",
        "xem đơn",
        "xem don",
        "trạng thái đơn",
        "trang thai don",
        "đơn hàng",
        "don hang",
    )

    @staticmethod
    def _extract_order_id(text: str) -> str | None:
        match = ORDER_ID_PATTERN.search(text)
        return match.group(0).upper() if match else None

    @staticmethod
    def _extract_reason(text: str) -> str:
        normalized = " ".join(text.strip().split())
        patterns = (
            r"(?:vì|vi)\s+(.+)$",
            r"(?:do)\s+(.+)$",
            r"(?:lý do|ly do)\s*[:\-]?\s*(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip(" .")
        return "chưa cung cấp lý do cụ thể"

    @staticmethod
    def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
        return any(hint in text for hint in hints)

    def create_plan(self, user_input: str) -> ExecutionPlan:
        question = " ".join(user_input.strip().split())
        folded = question.casefold()
        order_id = self._extract_order_id(question)
        asks_return = self._contains_any(folded, self.RETURN_HINTS)
        asks_plan = self._contains_any(folded, self.PLAN_HINTS)
        asks_policy = self._contains_any(folded, self.POLICY_HINTS)

        if asks_plan or (order_id and asks_return):
            reason = self._extract_reason(question)
            if not order_id:
                return ExecutionPlan(
                    goal="Lập phương án trả hàng cho một đơn cụ thể",
                    intent="return_options",
                    steps=[
                        PlanStep(
                            id=1,
                            description="Yêu cầu người quản lý cung cấp mã đơn cần xử lý",
                            suggested_tool=None,
                            depends_on=[],
                        )
                    ],
                    missing_information=["order_id"],
                    reason=reason,
                )
            return ExecutionPlan(
                goal=f"Đề xuất phương án trả hàng cho đơn {order_id}",
                intent="return_options",
                steps=[
                    PlanStep(1, "Tra cứu chính xác thông tin đơn hàng", "lookup_order", []),
                    PlanStep(2, "Tra cứu chính sách trả hàng liên quan", "search_policy", [1]),
                    PlanStep(3, "Xây dựng các phương án xử lý để quản lý lựa chọn", "build_return_options", [1, 2]),
                    PlanStep(4, "Trình bày các phương án và chờ quản lý chọn", None, [3]),
                ],
                order_id=order_id,
                reason=reason,
            )

        if order_id:
            return ExecutionPlan(
                goal=f"Tra cứu đơn {order_id}",
                intent="order_lookup",
                steps=[PlanStep(1, "Tra cứu chính xác đơn hàng", "lookup_order", [])],
                order_id=order_id,
            )

        if asks_policy or asks_return:
            return ExecutionPlan(
                goal="Trả lời câu hỏi chính sách đổi trả",
                intent="policy_question",
                steps=[PlanStep(1, "Tìm các điều khoản policy liên quan", "search_policy", [])],
            )

        if self._contains_any(folded, self.LOOKUP_HINTS):
            return ExecutionPlan(
                goal="Tra cứu một đơn hàng",
                intent="order_lookup",
                steps=[
                    PlanStep(
                        1,
                        "Yêu cầu người quản lý cung cấp mã đơn cần tra cứu",
                        None,
                        [],
                    )
                ],
                missing_information=["order_id"],
            )

        return ExecutionPlan(
            goal="Xác định yêu cầu nghiệp vụ",
            intent="unsupported",
            steps=[],
            missing_information=["business_intent"],
        )
