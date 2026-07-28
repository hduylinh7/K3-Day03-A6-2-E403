# MỐC 2 — CHATBOT FAQ CHROMA RAG

## Kiến trúc

```text
User question
→ exact retrieval cho mã đơn, SKU, size
→ semantic vector retrieval bằng Chroma
→ context [KB1..n]
→ một lần gọi Gemini
→ final answer
```

Chatbot không có ReAct loop, không gọi tool theo quyết định của model và không có
quyền ghi dữ liệu.

## Lý do dùng hybrid retrieval

- Vector search hiểu câu diễn đạt tự nhiên như “mặc không vừa thì gửi lại sao”.
- Exact lookup bảo vệ các định danh như `DH1024`, SKU và size khỏi bị tìm nhầm.
- Khi mã đơn không tồn tại, hệ thống không đưa đơn gần giống vào context.

## Test cases

1. “Trả hàng như nào?” → policy trả hàng.
2. “Tôi mặc không vừa...” → semantic paraphrase.
3. “Size M còn bao nhiêu?” → exact metadata filter, tổng hợp tồn kho.
4. “DH999” → not found, không bịa.
5. “DH1024 đổi size M?” → order + product + policy.

## Guardrails

- Read-only, không tạo yêu cầu hoặc giữ hàng.
- Chỉ dùng context RAG cho dữ liệu nghiệp vụ.
- Câu hỏi policy chung không bắt buộc mã đơn.
- Không dùng đơn gần giống thay cho mã đơn không tồn tại.
