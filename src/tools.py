"""Small, explicit tool set for the order return AI agent.

Main read tools:
1. lookup_order
2. search_policy
3. build_return_options

Optional write tool:
4. create_return_request

The LLM never mutates business data directly. Every tool validates its inputs
and returns one JSON-serializable observation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable

from knowledge_base import ChromaKnowledgeBase, get_knowledge_base

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
CONFIG_DIR = PROJECT_ROOT / "config"
ORDERS_PATH = CONFIG_DIR / "mock_orders.json"
REQUESTS_PATH = CONFIG_DIR / "mock_after_sales_requests.json"
POLICY_RULES_PATH = CONFIG_DIR / "policy_rules.json"

ACTIVE_REQUEST_STATUSES = {
    "pending_review",
    "approved",
    "awaiting_return",
    "received_by_warehouse",
    "processing",
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict[str, Any]]
    side_effect: str = "read_only"
    requires_confirmation: bool = False

    def declaration(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "side_effect": self.side_effect,
            "requires_confirmation": self.requires_confirmation,
        }


class ToolRegistry:
    """Validate and execute registered tools only."""

    def __init__(self, specs: list[ToolSpec]):
        self._specs = {spec.name: spec for spec in specs}

    @property
    def names(self) -> list[str]:
        return sorted(self._specs)

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def declarations(self) -> list[dict[str, Any]]:
        return [self._specs[name].declaration() for name in self.names]

    def catalog_text(self) -> str:
        return json.dumps(self.declarations(), ensure_ascii=False, indent=2)

    def execute(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        spec = self.get(name)
        if spec is None:
            return _error("UNKNOWN_TOOL", f"Tool '{name}' không tồn tại.", valid_tools=self.names)
        if not isinstance(arguments, dict):
            return _error("INVALID_ARGUMENTS", "Tool arguments phải là JSON object.")
        validation_error = _validate_arguments(spec.parameters, arguments)
        if validation_error:
            return _error("INVALID_ARGUMENTS", validation_error)
        if spec.requires_confirmation and arguments.get("confirmed") is not True:
            return _error(
                "CONFIRMATION_REQUIRED",
                "Hành động ghi dữ liệu cần xác nhận rõ ràng ở một lượt riêng.",
            )
        try:
            result = spec.handler(**arguments)
        except TypeError as exc:
            return _error("INVALID_ARGUMENTS", f"Không gọi được tool: {exc}")
        except Exception as exc:  # pragma: no cover
            return _error("TOOL_EXCEPTION", f"Tool gặp lỗi ngoài dự kiến: {exc}")
        if not isinstance(result, dict):
            return _error("INVALID_TOOL_RESULT", "Tool phải trả JSON object.")
        return result


def _ok(**payload: Any) -> dict[str, Any]:
    return {"ok": True, **payload}


def _error(code: str, message: str, **payload: Any) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "message": message, **payload}


def _load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"Không tìm thấy file {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} phải chứa JSON object.")
    return data


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as temp:
        json.dump(data, temp, ensure_ascii=False, indent=2)
        temp.write("\n")
        temporary_path = Path(temp.name)
    temporary_path.replace(path)


def _orders() -> list[dict[str, Any]]:
    rows = _load_json(ORDERS_PATH).get("orders", [])
    if not isinstance(rows, list):
        raise ValueError("mock_orders.json: orders phải là danh sách.")
    return rows




def _policy_rules() -> dict[str, Any]:
    return _load_json(
        POLICY_RULES_PATH,
        default={
            "return_window_days": 7,
            "excluded_sale_types": ["FINAL_SALE"],
            "manual_checks": [
                "Sản phẩm còn nguyên tem, nhãn và bao bì.",
                "Sản phẩm chưa qua sử dụng.",
            ],
            "personal_change_warning": "Lý do đổi ý cá nhân có thể bị từ chối theo policy.",
            "missing_reason_warning": "Chưa có lý do trả hàng rõ ràng.",
        },
    )

def _requests_data() -> dict[str, Any]:
    data = _load_json(
        REQUESTS_PATH,
        default={"data_version": "2026-07-28", "requests": []},
    )
    if not isinstance(data.get("requests", []), list):
        raise ValueError("mock_after_sales_requests.json: requests phải là danh sách.")
    return data


def _find_order(order_id: str) -> dict[str, Any] | None:
    target = order_id.strip().upper()
    return next(
        (row for row in _orders() if str(row.get("order_id", "")).upper() == target),
        None,
    )


def _active_requests(order: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    embedded = order.get("after_sales_request")
    if isinstance(embedded, dict) and embedded.get("status") in ACTIVE_REQUEST_STATUSES:
        results.append(embedded)
    target = str(order.get("order_id", "")).upper()
    for request in _requests_data().get("requests", []):
        if (
            str(request.get("order_id", "")).upper() == target
            and request.get("status") in ACTIVE_REQUEST_STATUSES
        ):
            results.append(request)
    return results


def _validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    required = schema.get("required", [])
    for field in required:
        if field not in arguments or arguments[field] in (None, ""):
            return f"Thiếu trường bắt buộc '{field}'."

    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            return f"Trường không được hỗ trợ: {unknown}."

    python_types: dict[str, Any] = {
        "string": str,
        "integer": int,
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    for field, value in arguments.items():
        rule = properties.get(field, {})
        expected = rule.get("type")
        if expected in python_types and not isinstance(value, python_types[expected]):
            return f"'{field}' phải có kiểu {expected}."
        if "enum" in rule and value not in rule["enum"]:
            return f"'{field}' phải thuộc {rule['enum']}."
        if isinstance(value, int):
            if "minimum" in rule and value < rule["minimum"]:
                return f"'{field}' phải >= {rule['minimum']}."
            if "maximum" in rule and value > rule["maximum"]:
                return f"'{field}' phải <= {rule['maximum']}."
    return None


# ---------------------------------------------------------------------------
# TOOL 1: ORDER LOOKUP
# ---------------------------------------------------------------------------

def lookup_order(order_id: str) -> dict[str, Any]:
    """Return one exact order and never guess a similar order ID."""
    target = order_id.strip().upper()
    order = _find_order(target)
    if order is None:
        return _error("ORDER_NOT_FOUND", f"Không tìm thấy đơn {target}.", order_id=target)

    items = order.get("items", []) if isinstance(order.get("items"), list) else []
    total_vnd = sum(
        int(item.get("quantity", 0)) * int(item.get("unit_price_vnd", 0))
        for item in items
    )
    return _ok(
        order={
            "order_id": target,
            "customer_id": order.get("customer_id"),
            "customer_display": order.get("customer_display"),
            "status": order.get("status"),
            "status_label": order.get("status_label"),
            "ordered_at": order.get("ordered_at"),
            "delivered_at": order.get("delivered_at"),
            "payment_method": order.get("payment_method"),
            "items": items,
            "total_vnd": total_vnd,
            "active_return_requests": _active_requests(order),
            "note": order.get("note", ""),
        }
    )


# ---------------------------------------------------------------------------
# TOOL 2: POLICY SEARCH
# ---------------------------------------------------------------------------

def search_policy(
    query: str,
    top_k: int = 5,
    *,
    knowledge_base: ChromaKnowledgeBase | None = None,
) -> dict[str, Any]:
    """Search only policy/FAQ chunks in Chroma."""
    kb = knowledge_base or get_knowledge_base()
    # Prefixing the query activates the policy-only retrieval guard in the KB.
    chunks, notes = kb.retrieve(f"chính sách đổi trả: {query}", history=None, top_k=max(top_k, 8))
    policy_chunks = [chunk for chunk in chunks if chunk.metadata.get("source") == "policy"]
    results = [
        {
            "id": chunk.doc_id,
            "title": chunk.metadata.get("title") or chunk.doc_id,
            "text": chunk.text,
            "distance": chunk.distance,
        }
        for chunk in policy_chunks[:top_k]
    ]
    if not results:
        return _error(
            "POLICY_NOT_FOUND",
            "Không tìm thấy điều khoản policy phù hợp.",
            query=query,
            notes=notes,
        )
    return _ok(query=query, notes=notes, result_count=len(results), results=results)


# ---------------------------------------------------------------------------
# TOOL 3: BUILD BUSINESS OPTIONS
# ---------------------------------------------------------------------------

def _days_since_delivery(order: dict[str, Any]) -> int | None:
    delivered_at = order.get("delivered_at")
    if not delivered_at:
        return None
    current = date.fromisoformat(os.getenv("MOCK_REFERENCE_DATE", "2026-07-28"))
    delivered = date.fromisoformat(str(delivered_at))
    return (current - delivered).days


def _reason_category(reason: str) -> str:
    folded = reason.casefold()
    if any(token in folded for token in ("lỗi", "loi", "hỏng", "hong", "giao sai", "thiếu", "thieu", "không đúng mô tả", "khong dung mo ta")):
        return "product_issue"
    if any(token in folded for token in ("không vừa", "khong vua", "chật", "chat", "rộng", "rong", "size", "cỡ")):
        return "fit_issue"
    if any(token in folded for token in ("không thích", "khong thich", "không ưng", "khong ung", "đổi ý", "doi y")):
        return "change_of_mind"
    return "unspecified"


def build_return_options(order_id: str, reason: str) -> dict[str, Any]:
    """Build manager-facing return options from hard business rules."""
    target = order_id.strip().upper()
    order = _find_order(target)
    if order is None:
        return _error("ORDER_NOT_FOUND", f"Không tìm thấy đơn {target}.")

    rules = _policy_rules()
    return_window_days = int(rules.get("return_window_days", 7))
    excluded_sale_types = {
        str(value).upper() for value in rules.get("excluded_sale_types", ["FINAL_SALE"])
    }
    blockers: list[str] = []
    warnings: list[str] = []
    days = _days_since_delivery(order)
    items = order.get("items", []) if isinstance(order.get("items"), list) else []

    if order.get("status") != "delivered":
        blockers.append(f"Đơn đang ở trạng thái {order.get('status_label')}, chưa thể mở quy trình trả hàng sau giao.")
    if days is None and order.get("status") == "delivered":
        blockers.append("Đơn đã giao nhưng thiếu ngày giao để tính thời hạn.")
    elif days is not None and days > return_window_days:
        blockers.append(
            f"Đơn đã quá thời hạn {return_window_days} ngày: hiện là {days} ngày từ lúc giao."
        )
    elif days is not None and days < 0:
        blockers.append("Ngày tham chiếu sớm hơn ngày giao hàng.")
    excluded_in_order = sorted({
        str(item.get("sale_type", "")).upper()
        for item in items
        if str(item.get("sale_type", "")).upper() in excluded_sale_types
    })
    if excluded_in_order:
        blockers.append(
            "Đơn có sản phẩm thuộc nhóm loại trừ " + ", ".join(excluded_in_order)
            + ", không thuộc diện đổi/trả thông thường."
        )
    if _active_requests(order):
        blockers.append("Đơn đã có yêu cầu hậu mãi đang hoạt động.")

    category = _reason_category(reason)
    if category == "unspecified":
        warnings.append(str(rules.get("missing_reason_warning")))
    elif category == "change_of_mind":
        warnings.append(str(rules.get("personal_change_warning")))

    manual_checks = [str(value) for value in rules.get("manual_checks", [])]

    options: list[dict[str, Any]] = []
    if not blockers:
        if category == "product_issue":
            options.extend(
                [
                    {
                        "option_id": "A",
                        "code": "RETURN_REFUND",
                        "title": "Trả hàng và xem xét hoàn tiền",
                        "request_type": "return",
                        "description": "Kho kiểm tra lỗi thực tế trước khi duyệt hoàn tiền.",
                        "recommended": True,
                    },
                    {
                        "option_id": "B",
                        "code": "EXCHANGE_PRODUCT",
                        "title": "Đổi sản phẩm tương đương",
                        "request_type": "exchange",
                        "description": "Phù hợp khi quản lý muốn ưu tiên đổi thay vì hoàn tiền; tồn kho cần kiểm tra ở bước xử lý sau.",
                        "recommended": False,
                    },
                ]
            )
        elif category == "fit_issue":
            options.extend(
                [
                    {
                        "option_id": "A",
                        "code": "EXCHANGE_SIZE",
                        "title": "Đổi size hoặc biến thể",
                        "request_type": "exchange",
                        "description": "Phù hợp nhất với lý do mặc không vừa; tồn kho size thay thế cần được nhân viên xác minh.",
                        "recommended": True,
                    },
                    {
                        "option_id": "B",
                        "code": "RETURN_REVIEW",
                        "title": "Gửi yêu cầu trả hàng để duyệt",
                        "request_type": "return",
                        "description": "Không bảo đảm hoàn tiền vì lý do không vừa không phải lỗi sản phẩm.",
                        "recommended": False,
                    },
                ]
            )
        else:
            options.extend(
                [
                    {
                        "option_id": "A",
                        "code": "RETURN_REVIEW",
                        "title": "Gửi yêu cầu trả hàng để duyệt",
                        "request_type": "return",
                        "description": "Kho và nhân viên hậu mãi sẽ kiểm tra lý do cùng tình trạng sản phẩm.",
                        "recommended": category != "change_of_mind",
                    },
                    {
                        "option_id": "B",
                        "code": "EXCHANGE_PRODUCT",
                        "title": "Chuyển sang phương án đổi hàng",
                        "request_type": "exchange",
                        "description": "Áp dụng nếu quản lý và khách thống nhất đổi sang sản phẩm khác.",
                        "recommended": category == "change_of_mind",
                    },
                ]
            )
        options.append(
            {
                "option_id": "C",
                "code": "MANUAL_REVIEW",
                "title": "Chuyển nhân viên kiểm tra thủ công",
                "request_type": "manual_review",
                "description": "Không tự động kết luận; nhân viên rà soát ảnh, tình trạng hàng và trao đổi với khách.",
                "recommended": False,
            }
        )
    else:
        options.append(
            {
                "option_id": "C",
                "code": "MANUAL_REVIEW",
                "title": "Chuyển nhân viên kiểm tra ngoại lệ",
                "request_type": "manual_review",
                "description": "Đơn không đạt điều kiện tự động; nhân viên chỉ tiếp nhận để rà soát ngoại lệ, không cam kết đổi hoặc hoàn tiền.",
                "recommended": True,
            }
        )

    return _ok(
        order_id=target,
        customer_id=order.get("customer_id"),
        reason=reason,
        reason_category=category,
        eligible_for_standard_return=not blockers,
        days_since_delivery=days,
        blockers=blockers,
        warnings=warnings,
        manual_checks=manual_checks,
        options=options,
    )


# ---------------------------------------------------------------------------
# OPTIONAL WRITE TOOL
# ---------------------------------------------------------------------------

def create_return_request(
    order_id: str,
    option_code: str,
    request_type: str,
    reason: str,
    confirmed: bool,
) -> dict[str, Any]:
    """Create one mock request after the manager chooses and confirms an option."""
    if confirmed is not True:
        return _error("CONFIRMATION_REQUIRED", "Cần xác nhận trước khi tạo yêu cầu.")
    target = order_id.strip().upper()
    order = _find_order(target)
    if order is None:
        return _error("ORDER_NOT_FOUND", f"Không tìm thấy đơn {target}.")
    if _active_requests(order):
        return _error("DUPLICATE_ACTIVE_REQUEST", "Đơn đã có yêu cầu hậu mãi đang hoạt động.")

    available = build_return_options(target, reason)
    if not available.get("ok"):
        return available
    selected = next(
        (row for row in available.get("options", []) if row.get("code") == option_code),
        None,
    )
    if selected is None:
        return _error("INVALID_OPTION", f"Phương án {option_code} không còn hợp lệ cho đơn {target}.")
    if selected.get("request_type") != request_type:
        return _error("OPTION_TYPE_MISMATCH", "Loại yêu cầu không khớp phương án đã chọn.")

    data = _requests_data()
    requests = data.setdefault("requests", [])
    known_ids: list[int] = []
    for request in requests:
        digits = "".join(char for char in str(request.get("request_id", "")) if char.isdigit())
        if digits:
            known_ids.append(int(digits))
    for known_order in _orders():
        embedded = known_order.get("after_sales_request")
        if isinstance(embedded, dict):
            digits = "".join(char for char in str(embedded.get("request_id", "")) if char.isdigit())
            if digits:
                known_ids.append(int(digits))
    request_id = f"ASR{(max(known_ids, default=0) + 1):04d}"

    record = {
        "request_id": request_id,
        "order_id": target,
        "customer_id": order.get("customer_id"),
        "option_code": option_code,
        "type": request_type,
        "reason": reason,
        "status": "pending_review",
        "status_label": "Đang chờ duyệt",
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "source": "ai_agent_mock",
    }
    requests.append(record)
    _atomic_write_json(REQUESTS_PATH, data)
    return _ok(
        message="Đã tạo yêu cầu mô phỏng.",
        request=record,
        note="Yêu cầu mới ở trạng thái chờ duyệt; chưa hoàn tiền hoặc giữ hàng.",
    )


def build_tool_registry(
    knowledge_base: ChromaKnowledgeBase | None = None,
) -> ToolRegistry:
    kb = knowledge_base or get_knowledge_base()

    def search_policy_bound(query: str, top_k: int = 5) -> dict[str, Any]:
        return search_policy(query, top_k, knowledge_base=kb)

    return ToolRegistry(
        [
            ToolSpec(
                name="lookup_order",
                description=(
                    "Tra cứu chính xác một đơn theo mã DH. Trả mã đơn, mã khách hàng, "
                    "trạng thái, ngày đặt/giao, sản phẩm, tổng tiền và yêu cầu hậu mãi hiện có."
                ),
                parameters={
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                    "required": ["order_id"],
                    "additionalProperties": False,
                },
                handler=lookup_order,
            ),
            ToolSpec(
                name="search_policy",
                description=(
                    "Tìm bất kỳ nội dung FAQ/chính sách đổi trả liên quan trong Chroma. "
                    "Tool chỉ trả các tài liệu có source=policy."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "minimum": 1, "maximum": 8},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=search_policy_bound,
            ),
            ToolSpec(
                name="build_return_options",
                description=(
                    "Đánh giá một đơn và tạo các phương án trả/đổi/chuyển kiểm tra để "
                    "người quản lý lựa chọn. Đây là tool lập phương án nghiệp vụ, không phải Planner của Agent."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["order_id", "reason"],
                    "additionalProperties": False,
                },
                handler=build_return_options,
            ),
            ToolSpec(
                name="create_return_request",
                description=(
                    "Tạo yêu cầu mô phỏng sau khi quản lý đã chọn phương án và xác nhận ở lượt riêng."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "option_code": {"type": "string"},
                        "request_type": {
                            "type": "string",
                            "enum": ["return", "exchange", "manual_review"],
                        },
                        "reason": {"type": "string"},
                        "confirmed": {"type": "boolean"},
                    },
                    "required": [
                        "order_id",
                        "option_code",
                        "request_type",
                        "reason",
                        "confirmed",
                    ],
                    "additionalProperties": False,
                },
                handler=create_return_request,
                side_effect="write_mock_data",
                requires_confirmation=True,
            ),
        ]
    )


AVAILABLE_TOOLS = {
    "lookup_order": lookup_order,
    "search_policy": search_policy,
    "build_return_options": build_return_options,
    "create_return_request": create_return_request,
}
