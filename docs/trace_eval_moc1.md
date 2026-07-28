# 📊 BÁO CÁO GIÁM SÁT & ĐÁNH GIÁ (OBSERVABILITY TRACE LOGS)

*Dành cho Role 5: Observability & Reviewer*

---

## 📍 MỐC 1 — ĐỊNH HÌNH BÀI TOÁN & AGENTIC FIT

### 1. Chủ đề đã chọn

**Trợ lý tra cứu đơn hàng và xử lý đổi trả cho người quản lý bán hàng/kho của doanh nghiệp nhỏ.**

### 2. Người dùng mục tiêu

- Chủ cửa hàng, quản lý bán hàng hoặc quản lý kho.
- Cần tra cứu nhanh trạng thái đơn, sản phẩm trong đơn và tồn kho.
- Cần kiểm tra điều kiện đổi/trả, chênh lệch hàng thay thế và tạo yêu cầu xử lý.
- Không yêu cầu người quản lý phải nhớ toàn bộ chính sách hoặc mở nhiều màn hình cùng lúc.

### 3. Phạm vi MVP của bài Lab

Agent phiên bản đầu chỉ xử lý dữ liệu mô phỏng, gồm:

1. Tra cứu đơn hàng theo mã đơn.
2. Kiểm tra đơn/sản phẩm có đủ điều kiện đổi hoặc trả hay không.
3. Kiểm tra tồn kho của sản phẩm muốn đổi.
4. Tính chênh lệch giá dự kiến khi đổi sản phẩm.
5. Tạo yêu cầu đổi/trả sau khi người dùng xác nhận rõ ràng.
6. Tra cứu trạng thái yêu cầu đổi/trả đã tạo.

**Ngoài phạm vi MVP:**

- Không tự động hoàn tiền thật.
- Không tự gọi đơn vị vận chuyển.
- Không sửa hoặc xóa đơn gốc.
- Không tạo yêu cầu đổi/trả khi chưa có xác nhận cuối cùng.
- Không xử lý dữ liệu khách hàng thật hoặc thông tin thanh toán thật.

### 4. Luồng nghiệp vụ đại diện

**Tình huống:**  
“Kiểm tra đơn `DH1024`. Khách muốn đổi áo đen size S sang size M vì mặc chật. Kho còn hàng không và đơn này có được đổi không?”

Luồng dự kiến:

```text
Tra cứu đơn hàng
→ Xác định đúng sản phẩm và trạng thái giao hàng
→ Kiểm tra điều kiện đổi trả
→ Kiểm tra tồn kho biến thể mới
→ Tính chênh lệch dự kiến nếu có
→ Tóm tắt phương án
→ Xin xác nhận
→ Tạo yêu cầu đổi hàng
```

Đây không phải một câu hỏi đáp cố định. Kết quả ở mỗi bước quyết định bước tiếp theo:

- Không tìm thấy đơn → dừng và yêu cầu kiểm tra lại mã đơn.
- Đơn chưa giao → không mở quy trình đổi/trả sau giao hàng.
- Hết thời hạn đổi trả → từ chối an toàn và nêu lý do.
- Sản phẩm mới hết kho → đề xuất trả hàng hoặc chọn biến thể khác.
- Có hàng và đủ điều kiện → xin xác nhận trước khi tạo yêu cầu.

---

## 🎯 5. BẢNG CHẤM ĐIỂM AGENTIC FIT (SCORING MATRIX)

| Tiêu chí | Điểm (1–5) | Lý do đánh giá |
| :--- | :---: | :--- |
| 🧠 **Multi-step Reasoning** | `5/5` | Một yêu cầu đổi hàng thường phải tra cứu đơn, xác định sản phẩm, kiểm tra chính sách, tồn kho, chênh lệch và bước xác nhận. |
| 🛠️ **Tool Interaction** | `5/5` | Cần đọc dữ liệu đơn hàng, tồn kho và ghi yêu cầu đổi/trả qua nhiều tool khác nhau; LLM không thể tự bịa các dữ liệu này. |
| 🔀 **Dynamic Decision** | `5/5` | Trạng thái đơn, lý do đổi trả, thời hạn chính sách và tồn kho làm thay đổi hoàn toàn đường xử lý. |
| ⏳ **Long Horizon** | `3/5` | Quy trình có khoảng 3–6 bước nhưng thường hoàn tất trong một phiên làm việc ngắn, chưa cần lập kế hoạch dài hạn. |
| **TỔNG ĐIỂM FIT** | **18/20** | **KẾT LUẬN: BÀI TOÁN RẤT PHÙ HỢP VỚI REACT AGENT.** |

### Kết luận Agentic Fit

ReAct Agent đáng dùng khi câu hỏi cần **dữ liệu nghiệp vụ thực tế**, **nhiều bước phụ thuộc nhau** hoặc **thay đổi trạng thái hệ thống**.

Tuy nhiên, không phải mọi câu hỏi đều cần Agent:

| Loại yêu cầu | Luồng phù hợp |
| :--- | :--- |
| “Cửa hàng cho đổi hàng trong bao lâu?” | Chatbot/FAQ path |
| “Đơn DH1024 hiện ở trạng thái nào?” | Agent gọi `lookup_order` |
| “Đơn DH1024 có đổi sang size M được không?” | ReAct Agent nhiều bước |
| “Tạo yêu cầu đổi sang size M giúp tôi.” | ReAct Agent + xác nhận trước hành động |

Điểm quan trọng: **Không nên dùng Agent cho mọi câu hỏi**. Với câu hỏi lý thuyết đơn giản, chatbot nhanh hơn, rẻ hơn và ít rủi ro hơn.

---

## 🧰 6. DANH SÁCH TOOL DỰ KIẾN CHO `src/tools.py`

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

## ⚠️ 7. FAILURE MODES DỰ KIẾN

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

## 🛡️ 8. NGUYÊN TẮC AN TOÀN CHỐT TỪ MỐC 1

1. Chỉ kết luận trạng thái đơn, tồn kho và điều kiện đổi/trả khi đã có Observation từ tool.
2. Không tự bịa mã đơn, SKU, chính sách, số lượng tồn hoặc trạng thái xử lý.
3. Mọi tool ghi dữ liệu phải yêu cầu xác nhận cuối cùng.
4. Không tạo hai yêu cầu đổi/trả cho cùng một sản phẩm nếu yêu cầu trước còn hiệu lực.
5. Không trả toàn bộ thông tin cá nhân của khách hàng.
6. Khi tool lỗi, Agent phải nói rõ chưa thể xác minh thay vì đoán.
7. Giới hạn số vòng lặp bằng `MAX_ITERATIONS`.
8. Dữ liệu lấy từ đơn hàng hoặc ghi chú khách hàng không được phép thay đổi system prompt.

---

## ✅ 9. CHECKLIST HOÀN THÀNH MỐC 1

- [x] Đã chọn chủ đề thực tế.
- [x] Đã mô tả người dùng và phạm vi MVP.
- [x] Đã chứng minh bài toán có nhu cầu dùng Agent.
- [x] Đã hoàn thành Scoring Matrix: **18/20**.
- [x] Đã liệt kê các tool dự kiến.
- [x] Đã xác định các failure modes chính.
- [x] Đã thống nhất guardrail cho hành động tạo yêu cầu.
- [x] Môi trường dự án đã được người dùng xác nhận setup xong.
- [ ] Chưa xác minh trực tiếp lệnh `python src/app.py` vì mã nguồn `src/app.py` không nằm trong các file được cung cấp ở lượt này.
- [ ] Chưa thực hiện Mốc 2.

---

## 🔄 10. LỆNH GIT SAU KHI CHÉP FILE VÀO DỰ ÁN

```bash
git add .
git commit -m "Moc 1: Agentic Fit cho tro ly don hang va doi tra"
git push
```
