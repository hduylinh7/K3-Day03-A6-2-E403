"""Chroma RAG knowledge base cho chatbot FAQ, không chứa Agent/tool loop."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv

load_dotenv()

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
CONFIG_DIR = PROJECT_ROOT / "config"

POLICY_PATH = CONFIG_DIR / "mock_policy.md"
ORDERS_PATH = CONFIG_DIR / "mock_orders.json"
PRODUCTS_PATH = CONFIG_DIR / "mock_products.json"

ORDER_ID_PATTERN = re.compile(r"\bDH\d{3,}\b", re.IGNORECASE)
SKU_PATTERN = re.compile(r"\b[A-Z0-9]+(?:-[A-Z0-9]+){2,}\b", re.IGNORECASE)
SIZE_PATTERN = re.compile(
    r"(?:\bsize\b|\bsz\b|\bcỡ\b)\s*[:\-]?\s*(XS|S|M|L|XL|XXL|\d{2})\b",
    re.IGNORECASE,
)


class KnowledgeBaseError(RuntimeError):
    """Lỗi khởi tạo, lập chỉ mục hoặc truy vấn knowledge base."""


class EmbeddingBackend(Protocol):
    name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Sinh vector cho tài liệu được lập chỉ mục."""

    def embed_query(self, text: str) -> list[float]:
        """Sinh vector cho câu hỏi truy xuất."""


@dataclass(frozen=True)
class KnowledgeDocument:
    doc_id: str
    text: str
    metadata: dict[str, str | int | float | bool]


@dataclass(frozen=True)
class RetrievedChunk:
    doc_id: str
    text: str
    metadata: dict[str, Any]
    distance: float | None = None


class GeminiEmbeddingBackend:
    """Embedding tiếng Việt bằng Gemini, dùng cùng GEMINI_API_KEY."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        self.dimension = int(os.getenv("GEMINI_EMBEDDING_DIMENSION", "768"))
        self.name = f"gemini:{self.model_name}:{self.dimension}"
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            raise KnowledgeBaseError(
                "Chưa có GEMINI_API_KEY để tạo embedding cho Chroma. "
                "Hãy điền key vào .env hoặc dùng --embedding-provider hash để test offline."
            )

        try:
            from google import genai
        except ImportError as exc:
            raise KnowledgeBaseError(
                "Chưa cài google-genai. Chạy: python -m pip install -U google-genai"
            ) from exc

        self._client = genai.Client(api_key=self.api_key)

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        try:
            from google.genai import types

            response = self._client.models.embed_content(
                model=self.model_name,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.dimension,
                ),
            )
            embeddings = getattr(response, "embeddings", None)
            if not embeddings or len(embeddings) != len(texts):
                raise KnowledgeBaseError("Gemini không trả đủ embedding cho dữ liệu đầu vào.")
            return [list(item.values) for item in embeddings]
        except KnowledgeBaseError:
            raise
        except Exception as exc:
            raise KnowledgeBaseError(f"Không tạo được Gemini embedding: {exc}") from exc

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, task_type="RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], task_type="QUESTION_ANSWERING")[0]


class HashEmbeddingBackend:
    """Embedding lexical deterministic để test offline, không dùng cho production."""

    name = "local-hash-v1"
    dimension = 384

    @staticmethod
    def _normalize(text: str) -> str:
        text = unicodedata.normalize("NFKC", text).casefold()
        return " ".join(re.findall(r"[\wÀ-ỹ]+", text, flags=re.UNICODE))

    def _vector(self, text: str) -> list[float]:
        normalized = self._normalize(text)
        tokens = normalized.split()
        features = tokens + [
            normalized[index : index + 3]
            for index in range(max(0, len(normalized) - 2))
            if " " not in normalized[index : index + 3]
        ]
        vector = [0.0] * self.dimension
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def create_embedding_backend(name: str | None = None) -> EmbeddingBackend:
    selected = (name or os.getenv("RAG_EMBEDDING_PROVIDER") or "gemini").strip().lower()
    if selected == "gemini":
        return GeminiEmbeddingBackend()
    if selected == "hash":
        return HashEmbeddingBackend()
    raise KnowledgeBaseError("RAG_EMBEDDING_PROVIDER chỉ hỗ trợ 'gemini' hoặc 'hash'.")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise KnowledgeBaseError(f"Không tìm thấy file dữ liệu: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise KnowledgeBaseError(f"JSON không hợp lệ trong {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise KnowledgeBaseError(f"{path.name} phải chứa một JSON object.")
    return data


def _slug(text: str) -> str:
    value = unicodedata.normalize("NFKD", text)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value[:60] or "section"


def _policy_documents(policy_text: str) -> list[KnowledgeDocument]:
    sections: list[tuple[str, list[str]]] = []
    current_title = "Tổng quan chính sách đổi trả"
    current_lines: list[str] = []

    for line in policy_text.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = line.removeprefix("## ").strip()
            current_lines = []
        elif not line.startswith("# "):
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, current_lines))

    synonyms = (
        "Các cách hỏi tương đương: đổi hàng, trả hàng, hoàn hàng, gửi lại hàng, "
        "đổi size, đổi màu, mặc không vừa, không ưng sản phẩm, hoàn tiền, refund."
    )
    documents: list[KnowledgeDocument] = []
    for index, (title, lines) in enumerate(sections, start=1):
        body = "\n".join(lines).strip()
        if not body:
            continue
        documents.append(
            KnowledgeDocument(
                doc_id=f"policy-{index:02d}-{_slug(title)}",
                text=f"Tiêu đề: {title}\n{body}\n\n{synonyms}",
                metadata={
                    "source": "policy",
                    "title": title,
                    "section": index,
                },
            )
        )
    return documents


def _order_documents(orders: list[dict[str, Any]]) -> list[KnowledgeDocument]:
    documents: list[KnowledgeDocument] = []
    for order in orders:
        order_id = str(order.get("order_id", "")).upper()
        item_lines = []
        for item in order.get("items", []):
            item_lines.append(
                "- {quantity} x {product_name}; SKU {sku}; biến thể {variant}; "
                "giá {price:,} đồng; loại bán {sale_type}.".format(
                    quantity=item.get("quantity", 0),
                    product_name=item.get("product_name", "Không rõ"),
                    sku=item.get("sku", "Không rõ"),
                    variant=item.get("variant", "Không rõ"),
                    price=int(item.get("unit_price_vnd", 0)),
                    sale_type=item.get("sale_type", "Không rõ"),
                )
            )
        after_sales = order.get("after_sales_request")
        after_sales_text = (
            json.dumps(after_sales, ensure_ascii=False)
            if after_sales
            else "Chưa có yêu cầu đổi trả."
        )
        text = (
            f"Mã đơn: {order_id}. Trạng thái: {order.get('status_label')} "
            f"({order.get('status')}). Ngày đặt: {order.get('ordered_at')}. "
            f"Ngày giao: {order.get('delivered_at') or 'chưa giao'}. "
            f"Thanh toán: {order.get('payment_method')}.\n"
            f"Sản phẩm trong đơn:\n" + "\n".join(item_lines) + "\n"
            f"Yêu cầu hậu mãi: {after_sales_text}\n"
            f"Ghi chú: {order.get('note', '')}"
        )
        documents.append(
            KnowledgeDocument(
                doc_id=f"order-{order_id}",
                text=text,
                metadata={
                    "source": "order",
                    "order_id": order_id,
                    "status": str(order.get("status", "unknown")),
                },
            )
        )
    return documents


def _product_documents(products: list[dict[str, Any]]) -> list[KnowledgeDocument]:
    documents: list[KnowledgeDocument] = []
    for product in products:
        sku = str(product.get("sku", "")).upper()
        stock = int(product.get("stock", 0))
        availability = "còn hàng" if stock > 0 else "hết hàng"
        text = (
            f"Sản phẩm: {product.get('product_name')}. SKU: {sku}. "
            f"Màu: {product.get('color')}. Size/cỡ: {product.get('size')}. "
            f"Giá: {int(product.get('price_vnd', 0)):,} đồng. "
            f"Tồn kho: {stock} sản phẩm, trạng thái {availability}. "
            f"Loại bán: {product.get('sale_type')}. "
            "Dữ liệu này dùng cho các câu hỏi còn hàng không, còn bao nhiêu, "
            "size nào có sẵn, màu nào có sẵn và chênh lệch giá."
        )
        documents.append(
            KnowledgeDocument(
                doc_id=f"product-{sku}",
                text=text,
                metadata={
                    "source": "product",
                    "sku": sku,
                    "product_name": str(product.get("product_name", "")),
                    "size": str(product.get("size", "")).upper(),
                    "color": str(product.get("color", "")),
                    "stock": stock,
                    "sale_type": str(product.get("sale_type", "")),
                },
            )
        )
    return documents


def build_documents() -> list[KnowledgeDocument]:
    policy_text = POLICY_PATH.read_text(encoding="utf-8")
    orders = _read_json(ORDERS_PATH).get("orders", [])
    products = _read_json(PRODUCTS_PATH).get("products", [])
    if not isinstance(orders, list) or not isinstance(products, list):
        raise KnowledgeBaseError("orders và products phải là danh sách.")
    return (
        _policy_documents(policy_text)
        + _order_documents(orders)
        + _product_documents(products)
    )


class ChromaKnowledgeBase:
    """Persistent Chroma DB với semantic retrieval và exact lookup overlay."""

    def __init__(self, embedding_provider: str | None = None) -> None:
        self.embedding_backend = create_embedding_backend(embedding_provider)
        db_setting = os.getenv("CHROMA_DB_PATH", ".chroma_db")
        db_path = Path(db_setting)
        self.db_path = db_path if db_path.is_absolute() else PROJECT_ROOT / db_path
        self.collection_name = os.getenv(
            "CHROMA_COLLECTION", "small_store_faq_v1"
        ).strip()
        self.top_k = max(1, int(os.getenv("RAG_TOP_K", "6")))
        self.reference_date = os.getenv("MOCK_REFERENCE_DATE", "2026-07-28")
        self._client: Any = None
        self._collection: Any = None

    def _import_chroma(self) -> Any:
        try:
            import chromadb
        except ImportError as exc:
            raise KnowledgeBaseError(
                "Chưa cài ChromaDB. Chạy: python -m pip install -U chromadb"
            ) from exc
        return chromadb

    def _state_path(self) -> Path:
        return self.db_path / f"{self.collection_name}.state.json"

    def _fingerprint(self) -> str:
        digest = hashlib.sha256()
        for path in (POLICY_PATH, ORDERS_PATH, PRODUCTS_PATH):
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        digest.update(self.embedding_backend.name.encode("utf-8"))
        digest.update(str(self.embedding_backend.dimension).encode("ascii"))
        return digest.hexdigest()

    def _get_client(self) -> Any:
        if self._client is None:
            chromadb = self._import_chroma()
            self.db_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.db_path))
        return self._client

    def _open_existing_collection(self) -> Any | None:
        client = self._get_client()
        try:
            return client.get_collection(
                name=self.collection_name,
                embedding_function=None,
            )
        except Exception:
            return None

    def _create_collection(self) -> Any:
        client = self._get_client()
        try:
            return client.create_collection(
                name=self.collection_name,
                embedding_function=None,
                configuration={"hnsw": {"space": "cosine"}},
                metadata={"description": "FAQ policy, orders and inventory"},
            )
        except (TypeError, ValueError):
            return client.create_collection(
                name=self.collection_name,
                embedding_function=None,
                metadata={
                    "description": "FAQ policy, orders and inventory",
                    "hnsw:space": "cosine",
                },
            )

    def ensure_index(self, force: bool = False) -> dict[str, Any]:
        documents = build_documents()
        expected_fingerprint = self._fingerprint()
        collection = self._open_existing_collection()
        state_path = self._state_path()
        state: dict[str, Any] = {}
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {}

        is_current = (
            not force
            and collection is not None
            and state.get("fingerprint") == expected_fingerprint
            and state.get("document_count") == len(documents)
            and collection.count() == len(documents)
        )
        if is_current:
            self._collection = collection
            return {
                "rebuilt": False,
                "document_count": len(documents),
                "embedding_backend": self.embedding_backend.name,
                "db_path": str(self.db_path),
            }

        client = self._get_client()
        if collection is not None:
            client.delete_collection(self.collection_name)
        collection = self._create_collection()

        texts = [document.text for document in documents]
        embeddings: list[list[float]] = []
        batch_size = 32
        for start in range(0, len(texts), batch_size):
            embeddings.extend(
                self.embedding_backend.embed_documents(texts[start : start + batch_size])
            )

        collection.add(
            ids=[document.doc_id for document in documents],
            documents=texts,
            metadatas=[document.metadata for document in documents],
            embeddings=embeddings,
        )
        state_path.write_text(
            json.dumps(
                {
                    "fingerprint": expected_fingerprint,
                    "document_count": len(documents),
                    "embedding_backend": self.embedding_backend.name,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._collection = collection
        return {
            "rebuilt": True,
            "document_count": len(documents),
            "embedding_backend": self.embedding_backend.name,
            "db_path": str(self.db_path),
        }

    def _collection_ready(self) -> Any:
        if self._collection is None:
            self.ensure_index()
        return self._collection

    @staticmethod
    def _history_text(history: list[dict[str, str]] | None) -> str:
        if not history:
            return ""
        return "\n".join(
            f"{item.get('role', '')}: {item.get('content', '')}"
            for item in history[-6:]
        )

    @staticmethod
    def _chunks_from_get(result: dict[str, Any]) -> list[RetrievedChunk]:
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        return [
            RetrievedChunk(
                doc_id=doc_id,
                text=document or "",
                metadata=metadata or {},
            )
            for doc_id, document, metadata in zip(ids, documents, metadatas)
        ]

    def retrieve(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
        top_k: int | None = None,
    ) -> tuple[list[RetrievedChunk], list[str]]:
        collection = self._collection_ready()
        combined = f"{self._history_text(history)}\n{question}".strip()
        order_ids = sorted({value.upper() for value in ORDER_ID_PATTERN.findall(combined)})
        skus = sorted({value.upper() for value in SKU_PATTERN.findall(combined)})
        sizes = sorted({value.upper() for value in SIZE_PATTERN.findall(combined)})

        order_records = _read_json(ORDERS_PATH).get("orders", [])
        selected_order_product_names = {
            str(item.get("product_name", "")).casefold()
            for order in order_records
            if str(order.get("order_id", "")).upper() in order_ids
            for item in order.get("items", [])
            if item.get("product_name")
        }
        question_folded = combined.casefold()
        requested_categories = {
            category
            for category in ("áo", "quần", "giày")
            if category in question_folded
        }
        policy_hints = (
            "đổi", "trả", "hoàn", "gửi lại", "không vừa", "không ưng",
            "tem", "nhãn", "phí", "bao lâu", "mấy ngày", "chính sách",
        )
        policy_only_query = (
            not order_ids
            and not skus
            and not sizes
            and any(hint in question_folded for hint in policy_hints)
        )

        chunks: list[RetrievedChunk] = []
        notes: list[str] = []
        seen: set[str] = set()

        def add_candidates(candidates: list[RetrievedChunk]) -> None:
            for candidate in candidates:
                if candidate.doc_id not in seen:
                    seen.add(candidate.doc_id)
                    chunks.append(candidate)

        if order_ids:
            exact_order_ids = [f"order-{order_id}" for order_id in order_ids]
            result = collection.get(
                ids=exact_order_ids,
                include=["documents", "metadatas"],
            )
            exact_chunks = self._chunks_from_get(result)
            add_candidates(exact_chunks)
            found = {
                str(chunk.metadata.get("order_id", "")).upper()
                for chunk in exact_chunks
            }
            for missing in sorted(set(order_ids) - found):
                notes.append(f"Không tìm thấy mã đơn {missing} trong knowledge base.")

        if skus:
            result = collection.get(
                ids=[f"product-{sku}" for sku in skus],
                include=["documents", "metadatas"],
            )
            add_candidates(self._chunks_from_get(result))

        for size in sizes:
            result = collection.get(
                where={"size": size},
                include=["documents", "metadatas"],
            )
            size_candidates = self._chunks_from_get(result)
            if selected_order_product_names:
                size_candidates = [
                    chunk
                    for chunk in size_candidates
                    if str(chunk.metadata.get("product_name", "")).casefold()
                    in selected_order_product_names
                ]
            elif requested_categories:
                size_candidates = [
                    chunk
                    for chunk in size_candidates
                    if any(
                        category
                        in str(chunk.metadata.get("product_name", "")).casefold()
                        for category in requested_categories
                    )
                ]
            add_candidates(size_candidates)

        # Nếu người dùng nêu một mã đơn không tồn tại, không kéo các đơn khác
        # vào context vì chúng dễ khiến LLM trả lời nhầm mã gần giống.
        missing_explicit_order = bool(order_ids) and not any(
            chunk.metadata.get("source") == "order" for chunk in chunks
        )

        query_vector = self.embedding_backend.embed_query(combined)
        limit = min(top_k or self.top_k, max(1, collection.count()))
        query_result = collection.query(
            query_embeddings=[query_vector],
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )
        batch_ids = (query_result.get("ids") or [[]])[0]
        batch_docs = (query_result.get("documents") or [[]])[0]
        batch_meta = (query_result.get("metadatas") or [[]])[0]
        batch_dist = (query_result.get("distances") or [[]])[0]
        semantic_chunks: list[RetrievedChunk] = []
        for doc_id, document, metadata, distance in zip(
            batch_ids, batch_docs, batch_meta, batch_dist
        ):
            metadata = metadata or {}
            source = metadata.get("source")
            if policy_only_query and source != "policy":
                continue
            if missing_explicit_order and source == "order":
                continue
            if order_ids and source == "order":
                candidate_order = str(metadata.get("order_id", "")).upper()
                if candidate_order not in order_ids:
                    continue
            if sizes and source == "product":
                if str(metadata.get("size", "")).upper() not in sizes:
                    continue
            if selected_order_product_names and source == "product":
                if str(metadata.get("product_name", "")).casefold() not in selected_order_product_names:
                    continue
            elif requested_categories and source == "product":
                product_name = str(metadata.get("product_name", "")).casefold()
                if not any(category in product_name for category in requested_categories):
                    continue
            semantic_chunks.append(
                RetrievedChunk(
                    doc_id=doc_id,
                    text=document or "",
                    metadata=metadata,
                    distance=float(distance) if distance is not None else None,
                )
            )
        add_candidates(semantic_chunks)
        return chunks[: max(10, limit + 4)], notes

    def build_context(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        chunks, notes = self.retrieve(question, history)
        blocks = [f"NGÀY THAM CHIẾU: {self.reference_date}"]
        for note in notes:
            blocks.append(f"THÔNG BÁO TRA CỨU: {note}")
        for index, chunk in enumerate(chunks, start=1):
            source = chunk.metadata.get("source", "unknown")
            title = (
                chunk.metadata.get("title")
                or chunk.metadata.get("order_id")
                or chunk.metadata.get("sku")
                or chunk.doc_id
            )
            distance = (
                f"; distance={chunk.distance:.4f}"
                if chunk.distance is not None
                else ""
            )
            blocks.append(
                f"[KB{index}] source={source}; id={chunk.doc_id}; title={title}{distance}\n"
                f"{chunk.text}"
            )
        if not chunks:
            blocks.append("Không truy xuất được tài liệu phù hợp.")
        return "\n\n".join(blocks)


_KB_CACHE: dict[str, ChromaKnowledgeBase] = {}


def get_knowledge_base(embedding_provider: str | None = None) -> ChromaKnowledgeBase:
    key = (embedding_provider or os.getenv("RAG_EMBEDDING_PROVIDER") or "gemini").lower()
    if key not in _KB_CACHE:
        _KB_CACHE[key] = ChromaKnowledgeBase(key)
    return _KB_CACHE[key]
