"""LLM provider cho Gemini và Mock Provider phục vụ kiểm thử offline."""

from __future__ import annotations

import os
import re
from typing import Protocol

from dotenv import load_dotenv

load_dotenv()


class BaseLLMProvider(Protocol):
    """Contract tối thiểu cho provider mà chatbot sử dụng."""

    model_name: str

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Sinh một câu trả lời từ prompt và system prompt."""


class GeminiProvider:
    """Google Gemini thông qua package ``google-genai``."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
        self.max_output_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "800"))

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return (
                "[Gemini Error] Chưa có GEMINI_API_KEY. Hãy thêm key vào file "
                ".env rồi chạy lại."
            )

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt or None,
                    temperature=self.temperature,
                    max_output_tokens=self.max_output_tokens,
                ),
            )
            text = getattr(response, "text", None)
            if not text:
                return "[Gemini Error] Model không trả về nội dung văn bản."
            return text.strip()
        except ImportError:
            return (
                "[Gemini Error] Chưa cài package google-genai. Chạy: "
                "python -m pip install -U google-genai"
            )
        except Exception as exc:
            return f"[Gemini Exception] {exc}"


class MockProvider:
    """Provider deterministic để test output, không thay thế Gemini thật."""

    model_name = "offline-chroma-rag-mock-v3"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        marker = "CÂU HỎI HIỆN TẠI:"
        current_question = prompt.split(marker, 1)[-1]
        current_question = current_question.split("Hãy trả lời", 1)[0].strip()
        text = current_question.casefold()

        if "dh999" in text:
            return "Không tìm thấy đơn DH999 trong knowledge base. Bạn hãy kiểm tra lại mã đơn."

        if any(phrase in text for phrase in ("tạo yêu cầu", "giữ hàng", "hủy đơn", "hoàn tiền giúp")):
            return (
                "Tôi chỉ là chatbot tra cứu nên không thể tạo yêu cầu, giữ hàng, "
                "hủy đơn hoặc thực hiện hoàn tiền."
            )

        if "trả hàng" in text or "gửi lại" in text or "không ưng" in text:
            return (
                "Theo policy mock, khách gửi yêu cầu trả hàng trong 7 ngày từ ngày "
                "giao thành công. Sản phẩm cần còn tem nhãn, chưa sử dụng và không "
                "thuộc FINAL_SALE. Trả do lỗi, giao sai hoặc không đúng mô tả được "
                "xem xét; đổi ý cá nhân có thể bị từ chối."
            )

        if "dh1024" in text:
            return (
                "Đơn DH1024 đã giao ngày 25/07/2026, gồm áo thun Basic đen size S. "
                "Size M còn 12 và cùng giá 249.000 đồng. Đơn còn trong thời hạn 7 "
                "ngày, nhưng vẫn phải kiểm tra tem nhãn và tình trạng sử dụng."
            )

        if "size m" in text or "cỡ m" in text:
            return (
                "Dữ liệu tồn kho có tổng 19 sản phẩm size M: Áo thun Basic đen "
                "còn 12 và Quần kaki Slim be còn 7."
            )

        return (
            "Tôi chưa đủ dữ liệu để kết luận. Hãy nêu câu hỏi policy, mã đơn, "
            "SKU hoặc đặc điểm sản phẩm cần kiểm tra."
        )

def get_llm_provider(provider_name: str | None = None) -> BaseLLMProvider:
    """Khởi tạo provider từ ``LLM_PROVIDER``; mặc định là Gemini."""
    name = (provider_name or os.getenv("LLM_PROVIDER") or "gemini").strip().lower()
    if name == "mock":
        return MockProvider()
    if name == "gemini":
        return GeminiProvider()
    raise ValueError("LLM_PROVIDER chỉ hỗ trợ 'gemini' hoặc 'mock' ở Mốc 2.")
