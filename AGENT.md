Hãy xây dựng MVP chatbot nội bộ dành cho nhân viên CSKH và vận hành, dùng để tra cứu thông tin khách hàng, đơn hàng, vận chuyển và chính sách đổi trả.

## Công nghệ

* Python 3.11+
* FastAPI
* Pydantic 2
* OpenAI-compatible API
* Pytest

Chưa sử dụng database. Toàn bộ dữ liệu được lưu trong các file JSON mock.

## Chức năng

Chatbot cần xử lý được:

* Tìm khách hàng theo mã, tên, số điện thoại hoặc email.
* Xem các đơn hàng của khách.
* Xem chi tiết đơn hàng và sản phẩm.
* Kiểm tra trạng thái vận chuyển.
* Tra cứu chính sách đổi trả.
* Kiểm tra đơn còn đủ điều kiện đổi trả hay không.
* Ghi nhớ khách hàng và đơn hàng trong hội thoại nhiều lượt.

Ví dụ:

* “Kiểm tra đơn ORD001.”
* “Đơn này đang giao đến đâu?”
* “Khách số 0987654321 có những đơn nào?”
* “Đơn này còn được đổi không?”
* “Chính sách đổi trả ngành thời trang là gì?”

## Dữ liệu mock

Tạo thư mục:

```text
data/
├── customers.json
├── products.json
├── orders.json
├── shipments.json
└── return_policies.json
```

Dữ liệu cần có đủ các trường hợp:

* Đơn đã giao và còn hạn đổi trả.
* Đơn đã giao nhưng quá hạn.
* Đơn đang vận chuyển.
* Đơn bị hủy.
* Không tìm thấy khách hàng hoặc đơn hàng.

## Kiến trúc

```text
API → Agent → Tool → Service → JSON Data
```

Agent không được đọc file JSON trực tiếp. Tool gọi service, service đọc và xử lý dữ liệu JSON.

## Tool bắt buộc

Tạo các tool read-only:

* `search_customer`
* `get_customer_orders`
* `get_order_detail`
* `get_shipping_status`
* `get_return_policy`
* `check_return_eligibility`

`check_return_eligibility` phải dùng rule-based service, không để LLM tự quyết định.

Rule tối thiểu:

* Đơn phải tồn tại.
* Sản phẩm phải thuộc đơn.
* Đơn phải ở trạng thái `delivered`.
* Chính sách phải còn hiệu lực.
* Yêu cầu phải nằm trong thời hạn đổi trả.
* Lý do không thuộc danh sách loại trừ.
* Nếu cần ảnh hoặc bằng chứng thì báo thông tin còn thiếu.

## API

Tạo các endpoint:

* `POST /api/v1/chat`
* `GET /api/v1/health`
* `GET /api/v1/tools`

Request chat:

```json
{
  "employee_id": "EMP001",
  "session_id": "SESSION001",
  "message": "Kiểm tra giúp tôi đơn ORD001"
}
```

Response gồm:

* Câu trả lời.
* Tool đã sử dụng.
* Dữ liệu chính.
* Trạng thái xử lý.
* Có cần nhân viên bổ sung thông tin hay không.

## Nguyên tắc Agent

* Chỉ trả lời dựa trên dữ liệu từ tool.
* Không bịa thông tin.
* Không hiển thị chain-of-thought.
* Không tạo, sửa hoặc xóa dữ liệu.
* Tối đa 6 lần gọi tool cho mỗi request.
* Nếu thiếu thông tin thì hỏi lại nhân viên.
* Lưu session state trong memory để hiểu các câu như “đơn này”, “khách đó”.

## Cấu trúc gợi ý
cấu trúc theo chuẩn trong src nhé, cố ko tự tạo thêm các thư mục mới.

Trước tiên hãy kiểm tra repository hiện tại, sau đó trực tiếp tạo code theo thứ tự:

1. Tạo JSON mock data.
2. Tạo service đọc và xử lý JSON.
3. Tạo các tool read-only.
4. Tạo LLM client và agent tool-calling.
5. Tạo Chat API.
6. Viết test và README.

Sau mỗi bước, chạy test và sửa lỗi trước khi tiếp tục. Không chỉ viết hướng dẫn, hãy trực tiếp tạo và chỉnh sửa code trong repository.
