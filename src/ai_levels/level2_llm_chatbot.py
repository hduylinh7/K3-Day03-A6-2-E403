"""
🤖 LEVEL 4: LLM CHATBOT + MEMORY + TOOL CALLING

Có:
- Intent Detection
- Conversation Memory
- Tool Simulation
- Context Awareness
"""


class AdvancedChatbot:

    def __init__(self):
        self.memory = []

        self.system_prompt = """
        Bạn là AI Assistant thông minh.
        Trả lời thân thiện, chính xác.
        Nếu cần dữ liệu realtime hãy sử dụng tool.
        """

    # -----------------------------
    # 1. Lưu lịch sử hội thoại
    # -----------------------------
    def save_memory(self, user, bot):

        self.memory.append({
            "user": user,
            "bot": bot
        })


    # -----------------------------
    # 2. Intent Detection
    # -----------------------------
    def detect_intent(self, text):

        text = text.lower()

        if "thời tiết" in text:
            return "weather"

        elif "vé" in text or "đặt vé" in text:
            return "booking"

        elif "giá" in text:
            return "price"

        else:
            return "general"


    # -----------------------------
    # 3. Tool Weather API giả lập
    # -----------------------------
    def weather_tool(self, city):

        weather_database = {
            "hà nội": "28°C, trời nhiều mây",
            "đà nẵng": "30°C, có nắng",
            "hồ chí minh": "32°C, nóng"
        }

        return weather_database.get(
            city.lower(),
            "Không tìm thấy dữ liệu thời tiết"
        )


    # -----------------------------
    # 4. Tool Booking
    # -----------------------------
    def booking_tool(self):

        return """
        Các chuyến bay phổ biến:

        Hà Nội → Đà Nẵng:
        1.500.000 VNĐ

        Hà Nội → TP.HCM:
        2.000.000 VNĐ
        """


    # -----------------------------
    # 5. Generate Response
    # -----------------------------
    def chat(self, user_input):

        intent = self.detect_intent(user_input)


        # TOOL CALL WEATHER
        if intent == "weather":

            if "hà nội" in user_input.lower():

                result = self.weather_tool("hà nội")

                response = (
                    f"🌤 Thời tiết Hà Nội hiện tại: {result}"
                )

            else:

                response = (
                    "Bạn muốn xem thời tiết thành phố nào?"
                )


        # TOOL CALL BOOKING
        elif intent == "booking":

            response = self.booking_tool()


        # PRICE
        elif intent == "price":

            response = (
                "💰 Giá dịch vụ từ 1.500.000 VNĐ."
            )


        # LLM RESPONSE
        else:

            response = (
                f"🤖 Tôi hiểu câu hỏi của bạn: "
                f"'{user_input}'. "
                "Tôi sẽ hỗ trợ bạn."
            )


        self.save_memory(
            user_input,
            response
        )

        return response



# ===============================
# DEMO
# ===============================


if __name__ == "__main__":


    bot = AdvancedChatbot()


    queries = [

        "Chào bạn",

        "Thời tiết Hà Nội hôm nay",

        "Tôi muốn đặt vé máy bay",

        "Giá vé bao nhiêu?"

    ]


    print(
        "=== ADVANCED LLM CHATBOT ===\n"
    )


    for q in queries:

        print("User:", q)

        print(
            "Bot:",
            bot.chat(q)
        )

        print("-"*50)