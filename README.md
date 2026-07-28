# Order Return AI Agent

Dự án có ba chế độ tách rõ để đúng rubric:

```text
baseline → 1 LLM call, không RAG, không tool
chatbot  → Chroma RAG read-only
agent    → Domain Planner + tool calling + manager selection + confirmation
```

## Kiến trúc Agent

```text
User request
→ DomainPlanner
→ lookup_order
→ search_policy
→ build_return_options
→ quản lý chọn A/B/C
→ xác nhận
→ create_return_request
```

Planner không phải tool. Planner tạo execution plan và dependency giữa các bước.
`/plan on` chỉ hiển thị plan, không bật hoặc tắt năng lực Planning.

## Tool chính

1. `lookup_order`
   - Input: `order_id`
   - Output: mã đơn, mã khách hàng, trạng thái, ngày đặt/giao, sản phẩm, tổng tiền.

2. `search_policy`
   - Input: câu hỏi policy.
   - Chỉ lấy Chroma chunks có `source=policy`.

3. `build_return_options`
   - Input: `order_id`, `reason`.
   - Output: blocker, warning và các phương án A/B/C cho quản lý chọn.

4. `create_return_request`
   - Tool ghi dữ liệu tùy chọn.
   - Chỉ chạy sau khi quản lý chọn phương án và xác nhận ở lượt riêng.

## Chạy dự án

```cmd
python -m pip install -r requirements_chroma.txt
copy .env.example .env
python src\app.py --rebuild-index --index-only
python src\app.py --mode agent
```

### Hiển thị Plan và Trace

```cmd
python src\app.py --mode agent --show-plan --show-trace
```

Trong phiên chat:

```text
/plan on
/trace on
```

### Test offline

```cmd
python src\app.py --mode agent --provider mock --embedding-provider hash --rebuild-index --test
```

## Ví dụ

```text
Bạn: lập phương án trả hàng cho DH1024 vì áo mặc không vừa

Plan:
1. lookup_order
2. search_policy
3. build_return_options
4. trình A/B/C

Bot:
A. Đổi size hoặc biến thể
B. Gửi yêu cầu trả hàng để duyệt
C. Chuyển nhân viên kiểm tra thủ công
```

Sau đó:

```text
Bạn: A
Bot: Xác nhận tạo yêu cầu?
Bạn: xác nhận
Bot: Đã tạo ASR... ở trạng thái Đang chờ duyệt.
```

## Flowchart

Sơ đồ nộp rubric nằm tại:

```text
docs/hybrid_flowchart.mermaid
```

## File quan trọng

```text
src/planner.py
src/tools.py
src/ai_levels/level3_reactive_agent.py
src/app.py
docs/hybrid_flowchart.mermaid
docs/trace_eval.md
config/test_cases_agent.json
```

## Giao diện web Streamlit

Cài dependencies:

```cmd
python -m pip install -r requirements.txt
```

Khởi chạy giao diện:

```cmd
python -m streamlit run streamlit_app.py
```

Trên Windows có thể nhấp đúp:

```text
run_ui.bat
```

Sau khi chạy, Streamlit sẽ mở trình duyệt tại địa chỉ thường là:

```text
http://localhost:8501
```

Giao diện hỗ trợ:

- Chat nhiều lượt với cùng một Agent session.
- Hiển thị hoặc ẩn execution plan.
- Hiển thị Action / Observation trace.
- Nút chọn trực tiếp phương án A/B/C.
- Nút xác nhận hoặc hủy trước tool ghi dữ liệu.
- Chuyển giữa Gemini/Mock và Gemini/Hash embedding.
- Xóa hội thoại và xây lại Chroma index.
