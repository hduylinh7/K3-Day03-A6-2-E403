# Chạy Chatbot FAQ bằng Chroma RAG + Gemini

## 1. Cài dependency

Không cần xóa `requirements.txt` hiện tại. Cài thêm phần RAG:

```cmd
python -m pip install -r requirements_chroma.txt
```

## 2. Cấu hình `.env`

```cmd
copy .env.example .env
notepad .env
```

Điền key thật:

```env
GEMINI_API_KEY=your_real_key
LLM_PROVIDER=gemini
RAG_EMBEDDING_PROVIDER=gemini
```

Một API key được dùng cho hai việc:

- `gemini-embedding-001`: tạo embedding cho Chroma.
- `gemini-2.5-flash`: viết câu trả lời cuối cùng.

Không commit `.env` hoặc thư mục `.chroma_db/`.

## 3. Tạo index lần đầu

```cmd
python src\app.py --rebuild-index --index-only
```

Lần đầu sẽ gọi Gemini Embedding API để index policy, đơn và sản phẩm. Những lần
sau Chroma đọc index persistent từ `.chroma_db` và chỉ rebuild khi dữ liệu nguồn
hoặc embedding model thay đổi.

## 4. Chạy chatbot

```cmd
python src\app.py
```

Thử:

```text
trả hàng như nào
Tôi mặc không vừa, muốn gửi lại thì sao?
Size M còn bao nhiêu sản phẩm?
Tra cứu đơn DH999
Đơn DH1024 đổi sang size M được không?
```

## 5. Xem Chroma đã lấy đoạn nào

```cmd
python src\app.py --show-context
```

Hoặc gõ `/context on` trong phiên chat.

## 6. Test offline

Offline mode vẫn dùng Chroma nhưng dùng vector hash lexical thay Gemini embedding:

```cmd
python src\app.py --rebuild-index --test --provider mock --embedding-provider hash
```

Hash mode chỉ để smoke test. Muốn hiểu câu hỏi tiếng Việt theo ngữ nghĩa tốt hơn,
dùng `RAG_EMBEDDING_PROVIDER=gemini`.

## Kiến trúc

```text
Câu hỏi tự nhiên
→ exact lookup mã đơn / SKU / size
→ semantic search trong Chroma
→ ghép các đoạn [KB]
→ gọi Gemini đúng 1 lần
→ câu trả lời read-only
```

Đây vẫn là chatbot RAG, chưa phải Agent: model không tự chọn tool, không chạy
Thought–Action–Observation và không thay đổi dữ liệu.
