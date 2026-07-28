"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
Các Tool deterministic cho đề tài tra cứu đơn hàng và xử lý đổi trả.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

POLICY_DATE = date(2026, 7, 28)
RETURN_WINDOW_DAYS = 7
ORDERS: dict[str, dict[str, Any]] = {
    "DH1024": {
        "order_id": "DH1024",
        "customer": "Nguyễn A.",
        "status": "delivered",
        "ordered_at": "2026-07-21",
        "delivered_at": "2026-07-24",
        "items": [
            {
                "sku": "AO-DEN-S",
                "product_name": "Áo thun Basic",
                "variant": "Đen / S",
                "quantity": 1,
                "unit_price": 199000,
                "returnable": True,
            }
        ],
    },
    "DH1025": {
        "order_id": "DH1025",
        "customer": "Trần B.",
        "status": "processing",
        "ordered_at": "2026-07-27",
        "delivered_at": None,
        "items": [
            {
                "sku": "AO-TRANG-M",
                "product_name": "Áo thun Basic",
                "variant": "Trắng / M",
                "quantity": 1,
                "unit_price": 199000,
                "returnable": True,
            }
        ],
    },
    "DH1001": {
        "order_id": "DH1001",
        "customer": "Lê C.",
        "status": "delivered",
        "ordered_at": "2026-06-18",
        "delivered_at": "2026-06-22",
        "items": [
            {
                "sku": "AO-DEN-M",
                "product_name": "Áo thun Basic",
                "variant": "Đen / M",
                "quantity": 1,
                "unit_price": 199000,
                "returnable": True,
            }
        ],
    },
}
INVENTORY: dict[str, int] = {
    "AO-DEN-S": 3,
    "AO-DEN-M": 8,
    "AO-DEN-L": 0,
    "AO-TRANG-M": 5,
}
PRODUCT_PRICES: dict[str, int] = {
    "AO-DEN-S": 199000,
    "AO-DEN-M": 199000,
    "AO-DEN-L": 219000,
    "AO-TRANG-M": 199000,
}

AFTER_SALES_REQUESTS: dict[str, dict[str, Any]] = {}
def _result(
    tool: str,
    success: bool,
    *,
    data: dict[str, Any] | None = None,
    error: str | None = None,
) -> str:
    """Chuẩn hóa mọi kết quả Tool thành JSON string, không quăng lỗi ra Agent."""
    payload: dict[str, Any] = {"tool": tool, "success": success}
    if data is not None:
        payload["data"] = data
    if error is not None:
        payload["error"] = error
    return json.dumps(payload, ensure_ascii=False)


def _normalize_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _find_item(order: dict[str, Any], sku: str) -> dict[str, Any] | None:
    normalized_sku = _normalize_text(sku).upper()
    return next(
        (item for item in order["items"] if item["sku"] == normalized_sku),
        None,
    )

def lookup_order(order_id: str) -> str:
    """
    Tra cứu một đơn hàng bằng mã đơn.

    Purpose:
        Dùng khi cần biết trạng thái, ngày giao và các sản phẩm trong đơn.
    Input:
        order_id: Mã đơn bắt buộc, ví dụ ``DH1024``.
    Output:
        JSON string chứa ``success`` và dữ liệu đơn đã tối thiểu hóa PII.
    Error semantics:
        Trả JSON ``success=false`` khi thiếu hoặc không tìm thấy mã đơn.
    Side effect:
        Read-only, không thay đổi dữ liệu.
    """
    normalized_id = _normalize_text(order_id).upper()
    if not normalized_id:
        return _result("lookup_order", False, error="Thiếu mã đơn hàng.")

    order = ORDERS.get(normalized_id)
    if order is None:
        return _result(
            "lookup_order",
            False,
            error=f"Không tìm thấy đơn hàng '{normalized_id}'.",
        )

    return _result("lookup_order", True, data=order)


def check_return_eligibility(order_id: str, sku: str, reason: str) -> str:
    """
    Kiểm tra một sản phẩm có đủ điều kiện đổi/trả hay không.

    Purpose:
        Dùng sau khi đã có mã đơn, SKU và lý do đổi/trả.
    Input:
        order_id: Mã đơn.
        sku: SKU thuộc đơn hàng.
        reason: Lý do khách yêu cầu đổi/trả.
    Output:
        JSON string gồm ``eligible``, hạn cuối và lý do kết luận.
    Error semantics:
        Không crash khi đơn/SKU sai; trả ``success=false`` hoặc
        ``eligible=false`` kèm lý do.
    Side effect:
        Read-only.
    """
    normalized_id = _normalize_text(order_id).upper()
    normalized_sku = _normalize_text(sku).upper()
    normalized_reason = _normalize_text(reason)
    if not normalized_id or not normalized_sku or not normalized_reason:
        return _result(
            "check_return_eligibility",
            False,
            error="Cần đủ order_id, sku và reason.",
        )

    order = ORDERS.get(normalized_id)
    if order is None:
        return _result(
            "check_return_eligibility",
            False,
            error=f"Không tìm thấy đơn hàng '{normalized_id}'.",
        )

    item = _find_item(order, normalized_sku)
    if item is None:
        return _result(
            "check_return_eligibility",
            False,
            error=f"SKU '{normalized_sku}' không thuộc đơn {normalized_id}.",
        )

    if order["status"] != "delivered" or not order["delivered_at"]:
        return _result(
            "check_return_eligibility",
            True,
            data={
                "eligible": False,
                "reason": "Đơn hàng chưa ở trạng thái đã giao.",
            },
        )

    if not item.get("returnable", False):
        return _result(
            "check_return_eligibility",
            True,
            data={
                "eligible": False,
                "reason": "Sản phẩm thuộc nhóm không hỗ trợ đổi/trả.",
            },
        )

    delivered_at = date.fromisoformat(order["delivered_at"])
    days_since_delivery = (POLICY_DATE - delivered_at).days
    deadline = delivered_at.fromordinal(
        delivered_at.toordinal() + RETURN_WINDOW_DAYS
    )

    has_active_request = any(
        request["order_id"] == normalized_id
        and request["original_sku"] == normalized_sku
        and request["status"] in {"created", "processing"}
        for request in AFTER_SALES_REQUESTS.values()
    )
    if has_active_request:
        return _result(
            "check_return_eligibility",
            True,
            data={
                "eligible": False,
                "reason": "Sản phẩm đã có yêu cầu hậu mãi đang xử lý.",
            },
        )

    eligible = 0 <= days_since_delivery <= RETURN_WINDOW_DAYS
    return _result(
        "check_return_eligibility",
        True,
        data={
            "eligible": eligible,
            "policy_date": POLICY_DATE.isoformat(),
            "delivered_at": delivered_at.isoformat(),
            "deadline": deadline.isoformat(),
            "days_since_delivery": days_since_delivery,
            "submitted_reason": normalized_reason,
            "reason": (
                "Đơn còn trong thời hạn đổi/trả."
                if eligible
                else f"Đơn đã quá thời hạn {RETURN_WINDOW_DAYS} ngày."
            ),
        },
    )


def check_inventory(sku: str, quantity: int = 1) -> str:
    """
    Kiểm tra tồn kho khả dụng của một SKU.

    Purpose:
        Dùng trước khi đề xuất hoặc tạo yêu cầu đổi sang sản phẩm khác.
    Input:
        sku: SKU cần kiểm tra.
        quantity: Số lượng nguyên dương, mặc định là 1.
    Output:
        JSON string gồm tồn kho hiện tại và ``available``.
    Error semantics:
        Trả lỗi có cấu trúc nếu SKU không tồn tại hoặc quantity không hợp lệ.
    Side effect:
        Read-only.
    """
    normalized_sku = _normalize_text(sku).upper()
    if not normalized_sku:
        return _result("check_inventory", False, error="Thiếu SKU.")

    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        return _result(
            "check_inventory",
            False,
            error="quantity phải là số nguyên dương.",
        )

    if normalized_sku not in INVENTORY:
        return _result(
            "check_inventory",
            False,
            error=f"Không tìm thấy SKU '{normalized_sku}' trong kho.",
        )

    stock = INVENTORY[normalized_sku]
    return _result(
        "check_inventory",
        True,
        data={
            "sku": normalized_sku,
            "requested_quantity": quantity,
            "stock": stock,
            "available": stock >= quantity,
        },
    )


def calculate_exchange_adjustment(
    order_id: str,
    original_sku: str,
    replacement_sku: str,
    quantity: int = 1,
) -> str:
    """
    Tính chênh lệch tiền dự kiến khi đổi sang SKU khác.

    Purpose:
        Dùng sau khi đã xác định sản phẩm gốc và sản phẩm thay thế.
    Input:
        order_id, original_sku, replacement_sku và quantity.
    Output:
        JSON string chứa đơn giá cũ, mới và chênh lệch bằng VNĐ.
    Error semantics:
        Trả lỗi có cấu trúc nếu đơn, SKU hoặc quantity không hợp lệ.
    Side effect:
        Read-only; chỉ tính toán, không thu hoặc hoàn tiền.
    """
    normalized_id = _normalize_text(order_id).upper()
    original = _normalize_text(original_sku).upper()
    replacement = _normalize_text(replacement_sku).upper()

    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        return _result(
            "calculate_exchange_adjustment",
            False,
            error="quantity phải là số nguyên dương.",
        )

    order = ORDERS.get(normalized_id)
    if order is None:
        return _result(
            "calculate_exchange_adjustment",
            False,
            error=f"Không tìm thấy đơn hàng '{normalized_id}'.",
        )

    item = _find_item(order, original)
    if item is None:
        return _result(
            "calculate_exchange_adjustment",
            False,
            error=f"SKU '{original}' không thuộc đơn {normalized_id}.",
        )

    if replacement not in PRODUCT_PRICES:
        return _result(
            "calculate_exchange_adjustment",
            False,
            error=f"Không tìm thấy giá của SKU thay thế '{replacement}'.",
        )

    old_total = int(item["unit_price"]) * quantity
    new_total = PRODUCT_PRICES[replacement] * quantity
    difference = new_total - old_total

    if difference > 0:
        direction = "customer_pays_more"
    elif difference < 0:
        direction = "business_refunds"
    else:
        direction = "no_difference"

    return _result(
        "calculate_exchange_adjustment",
        True,
        data={
            "order_id": normalized_id,
            "original_sku": original,
            "replacement_sku": replacement,
            "quantity": quantity,
            "old_total_vnd": old_total,
            "new_total_vnd": new_total,
            "difference_vnd": difference,
            "direction": direction,
        },
    )


def create_after_sales_request(
    order_id: str,
    request_type: str,
    original_sku: str,
    reason: str,
    replacement_sku: str = "",
    quantity: int = 1,
    confirmed: bool = False,
) -> str:
    """
    Tạo yêu cầu đổi hoặc trả hàng trong bộ nhớ mô phỏng.

    Purpose:
        Chỉ dùng ở bước cuối sau khi đã xác minh điều kiện và người dùng xác nhận.
    Input:
        request_type nhận ``exchange``/``return`` hoặc ``đổi``/``trả``;
        confirmed bắt buộc phải là ``True``.
    Output:
        JSON string chứa mã yêu cầu và trạng thái mới tạo.
    Error semantics:
        Từ chối khi thiếu xác nhận, đơn/SKU sai, không đủ điều kiện, hết kho
        hoặc đã tồn tại yêu cầu đang xử lý.
    Side effect:
        Write side effect trong bộ nhớ tiến trình; không tác động hệ thống thật.
    """
    normalized_id = _normalize_text(order_id).upper()
    original = _normalize_text(original_sku).upper()
    replacement = _normalize_text(replacement_sku).upper()
    normalized_type = _normalize_text(request_type).lower()
    normalized_reason = _normalize_text(reason)

    type_map = {
        "exchange": "exchange",
        "đổi": "exchange",
        "doi": "exchange",
        "return": "return",
        "trả": "return",
        "tra": "return",
    }
    mapped_type = type_map.get(normalized_type)

    if confirmed is not True:
        return _result(
            "create_after_sales_request",
            False,
            error="Chưa có xác nhận cuối cùng; không tạo yêu cầu.",
        )

    if mapped_type is None:
        return _result(
            "create_after_sales_request",
            False,
            error="request_type chỉ nhận exchange/return hoặc đổi/trả.",
        )

    eligibility_raw = check_return_eligibility(
        normalized_id,
        original,
        normalized_reason,
    )
    eligibility = json.loads(eligibility_raw)
    if not eligibility["success"]:
        return _result(
            "create_after_sales_request",
            False,
            error=eligibility["error"],
        )
    if not eligibility["data"]["eligible"]:
        return _result(
            "create_after_sales_request",
            False,
            error=eligibility["data"]["reason"],
        )

    if mapped_type == "exchange":
        if not replacement:
            return _result(
                "create_after_sales_request",
                False,
                error="Yêu cầu đổi hàng cần replacement_sku.",
            )
        inventory = json.loads(check_inventory(replacement, quantity))
        if not inventory["success"]:
            return _result(
                "create_after_sales_request",
                False,
                error=inventory["error"],
            )
        if not inventory["data"]["available"]:
            return _result(
                "create_after_sales_request",
                False,
                error=f"SKU '{replacement}' không đủ tồn kho.",
            )

    request_id = f"AS{len(AFTER_SALES_REQUESTS) + 1:04d}"
    request = {
        "request_id": request_id,
        "order_id": normalized_id,
        "request_type": mapped_type,
        "original_sku": original,
        "replacement_sku": replacement or None,
        "quantity": quantity,
        "reason": normalized_reason,
        "status": "created",
        "confirmed": True,
    }
    AFTER_SALES_REQUESTS[request_id] = request
    return _result("create_after_sales_request", True, data=request)


def get_after_sales_status(request_id: str) -> str:
    """
    Tra cứu trạng thái một yêu cầu đổi/trả đã tạo.

    Purpose:
        Dùng khi người quản lý cần theo dõi tiến độ hậu mãi.
    Input:
        request_id: Mã yêu cầu, ví dụ ``AS0001``.
    Output:
        JSON string chứa dữ liệu yêu cầu.
    Error semantics:
        Trả ``success=false`` nếu thiếu hoặc không tìm thấy mã.
    Side effect:
        Read-only.
    """
    normalized_id = _normalize_text(request_id).upper()
    if not normalized_id:
        return _result(
            "get_after_sales_status",
            False,
            error="Thiếu mã yêu cầu hậu mãi.",
        )

    request = AFTER_SALES_REQUESTS.get(normalized_id)
    if request is None:
        return _result(
            "get_after_sales_status",
            False,
            error=f"Không tìm thấy yêu cầu '{normalized_id}'.",
        )

    return _result("get_after_sales_status", True, data=request)


AVAILABLE_TOOLS = {
    "lookup_order": lookup_order,
    "check_return_eligibility": check_return_eligibility,
    "check_inventory": check_inventory,
    "calculate_exchange_adjustment": calculate_exchange_adjustment,
    "create_after_sales_request": create_after_sales_request,
    "get_after_sales_status": get_after_sales_status,
}


if __name__ == "__main__":
    print("=== SMOKE TEST TOOL REGISTRY ===")
    print(lookup_order("DH1024"))
    print(check_inventory("AO-DEN-M", 1))
