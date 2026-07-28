
## DANH SÁCH TOOL DỰ KIẾN CHO `src/tools.py`

| Tool | Mục đích | Loại tác động |
| :--- | :--- | :---: |
| `lookup_order` | Tra cứu thông tin đơn, khách hàng rút gọn, sản phẩm, số lượng, ngày mua và trạng thái giao hàng. | Read-only |
| `check_return_eligibility` | Kiểm tra sản phẩm có đủ điều kiện đổi/trả theo trạng thái đơn, thời hạn, lý do và lịch sử xử lý hay không. | Read-only |
| `check_inventory` | Kiểm tra tồn kho theo SKU, màu, size hoặc biến thể sản phẩm. | Read-only |
| `calculate_exchange_adjustment` | Tính chênh lệch giá và chi phí dự kiến khi đổi sang sản phẩm khác. | Read-only |
| `create_after_sales_request` | Tạo yêu cầu đổi hoặc trả sau khi người dùng xác nhận đầy đủ. | **Write / Side effect** |
| `get_after_sales_status` | Tra cứu trạng thái yêu cầu đổi/trả đã tạo. | Read-only |

### Chuỗi tool tối thiểu theo từng nhu cầu

```text
Tra cứu đơn:
lookup_order

Trả hàng:
lookup_order
→ check_return_eligibility
→ xác nhận người dùng
→ create_after_sales_request

Đổi hàng:
lookup_order
→ check_return_eligibility
→ check_inventory
→ calculate_exchange_adjustment
→ xác nhận người dùng
→ create_after_sales_request
```

---

## FAILURE MODES DỰ KIẾN

| Failure mode | Biểu hiện | Cách xử lý an toàn dự kiến |
| :--- | :--- | :--- |
| **Không tìm thấy mã đơn** | `lookup_order` không có dữ liệu | Trả lỗi nghiệp vụ rõ ràng, không đoán đơn tương tự. |
| **Thiếu mã đơn hoặc SKU** | Người dùng yêu cầu mơ hồ | Hỏi đúng một thông tin còn thiếu trước khi gọi tool. |
| **Đơn chưa giao hoặc đã hủy** | Không phù hợp quy trình đổi/trả sau giao hàng | Dừng luồng và giải thích trạng thái hiện tại. |
| **Quá hạn đổi/trả** | Không đạt điều kiện chính sách | Không tạo yêu cầu; nêu lý do từ Observation. |
| **Sản phẩm không được đổi/trả** | Hàng thuộc nhóm loại trừ | Từ chối an toàn, không tự “nới” chính sách. |
| **Đơn đã có yêu cầu xử lý** | Nguy cơ tạo yêu cầu trùng | Trả mã yêu cầu hiện có và không tạo bản ghi mới. |
| **Hết tồn kho sản phẩm thay thế** | Không thể hoàn tất đổi hàng | Đề xuất biến thể khác hoặc chuyển sang phương án trả hàng. |
| **Tồn kho thay đổi giữa lúc kiểm tra và tạo yêu cầu** | Dữ liệu cũ/race condition | Tool tạo yêu cầu phải kiểm tra lại tồn kho trước khi ghi. |
| **Sai kiểu hoặc cú pháp tham số** | Parser truyền thiếu/sai field | Tool trả lỗi có cấu trúc, không làm chương trình crash. |
| **Tool không tồn tại** | Model gọi nhầm tên tool | Trả danh sách tool hợp lệ và cho Agent tự sửa trong giới hạn vòng lặp. |
| **Tool timeout hoặc lỗi dữ liệu** | Không có Observation đáng tin cậy | Không khẳng định kết quả; trả fallback và đề nghị thử lại. |
| **Lặp lại cùng Action** | Agent gọi cùng tool và tham số nhiều lần | Chặn action trùng và dừng bằng `MAX_ITERATIONS`. |
| **Tạo yêu cầu khi chưa xác nhận** | Hành động ghi dữ liệu quá sớm | Guardrail bắt buộc xác nhận rõ loại yêu cầu, sản phẩm, số lượng và phương án. |
| **Lộ dữ liệu khách hàng** | Trả thừa số điện thoại/địa chỉ | Chỉ hiển thị dữ liệu tối thiểu, che thông tin nhạy cảm. |
| **Prompt injection từ ghi chú đơn hàng** | Nội dung dữ liệu yêu cầu Agent bỏ qua quy tắc | Xem dữ liệu tool là dữ liệu không đáng tin, không phải chỉ dẫn hệ thống. |

---

## NGUYÊN TẮC AN TOÀN CHỐT TỪ MỐC 1

1. Chỉ kết luận trạng thái đơn, tồn kho và điều kiện đổi/trả khi đã có Observation từ tool.
2. Không tự bịa mã đơn, SKU, chính sách, số lượng tồn hoặc trạng thái xử lý.
3. Mọi tool ghi dữ liệu phải yêu cầu xác nhận cuối cùng.
4. Không tạo hai yêu cầu đổi/trả cho cùng một sản phẩm nếu yêu cầu trước còn hiệu lực.
5. Không trả toàn bộ thông tin cá nhân của khách hàng.
6. Khi tool lỗi, Agent phải nói rõ chưa thể xác minh thay vì đoán.
7. Giới hạn số vòng lặp bằng `MAX_ITERATIONS`.
8. Dữ liệu lấy từ đơn hàng hoặc ghi chú khách hàng không được phép thay đổi system prompt.

---

