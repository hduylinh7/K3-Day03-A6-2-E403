# Cài đặt và chạy

## 1. Tạo môi trường

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements_chroma.txt
```

## 2. Tạo `.env`

```cmd
copy .env.example .env
notepad .env
```

Điền `GEMINI_API_KEY` thật trong `.env`. Không điền key thật vào `.env.example`.

## 3. Tạo Chroma index

```cmd
python src\app.py --rebuild-index --index-only
```

## 4. Chạy Agent

```cmd
python src\app.py --mode agent
```

Hiển thị plan và trace:

```cmd
python src\app.py --mode agent --show-plan --show-trace
```

## 5. Các mode

```cmd
python src\app.py --mode baseline
python src\app.py --mode chatbot
python src\app.py --mode agent
```

- `baseline`: không RAG, không tool.
- `chatbot`: Chroma RAG read-only.
- `agent`: Planner + ba tool chính + xác nhận hành động ghi.

## 6. Test offline

```cmd
python src\app.py --mode agent --provider mock --embedding-provider hash --rebuild-index --test
```

## 7. Ý nghĩa `/plan on`

`/plan on` chỉ in execution plan ra terminal. Planner luôn chạy với Agent, kể cả
khi `/plan off`.
