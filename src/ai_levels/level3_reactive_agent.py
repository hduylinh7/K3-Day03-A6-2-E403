"""
🧠 LEVEL 3: REACTIVE AGENT (ReAct Framework)

Thought
   ↓
Action
   ↓
Observation
   ↓
Thought
   ↓
Final Answer

Features:
- Multiple tools
- Dynamic tool selection
- ReAct loop
- Memory
"""


import time


# ==========================
# TOOL DEFINITIONS
# ==========================


def get_weather(city: str):

    weather_db = {

        "hà nội":
            {
                "temp": "28°C",
                "condition": "Nắng nhẹ",
                "humidity": "65%"
            },

        "đà nẵng":
            {
                "temp": "30°C",
                "condition": "Có nắng",
                "humidity": "70%"
            }
    }


    return weather_db.get(
        city.lower(),
        "Không có dữ liệu thời tiết"
    )



def search_flights(origin, destination):

    flights = {

        ("hà nội", "đà nẵng"):
            "VN123 - 1.500.000 VNĐ",

        ("hà nội", "hồ chí minh"):
            "VN201 - 2.000.000 VNĐ"

    }


    return flights.get(
        (
            origin.lower(),
            destination.lower()
        ),
        "Không tìm thấy chuyến bay"
    )



def clothing_advisor(weather):

    if "28°C" in weather:

        return (
            "Thời tiết mát, "
            "nên mặc áo phông và quần thoải mái."
        )

    return "Hãy chọn trang phục phù hợp."



# ==========================
# AGENT CORE
# ==========================


class ReactiveAgent:


    def __init__(self):

        self.memory = []



    # ---------------------
    # Agent Reasoning
    # ---------------------

    def think(self, goal):

        goal = goal.lower()


        if "thời tiết" in goal:

            return {
                "tool":
                "weather",

                "city":
                "hà nội"
            }


        elif "vé máy bay" in goal:

            return {

                "tool":
                "flight",

                "origin":
                "hà nội",

                "destination":
                "đà nẵng"
            }


        return {

            "tool":
            "none"

        }



    # ---------------------
    # Action Executor
    # ---------------------

    def act(self, action):


        tool = action["tool"]



        if tool == "weather":


            result = get_weather(
                action["city"]
            )

            return result



        elif tool == "flight":


            result = search_flights(
                action["origin"],
                action["destination"]
            )

            return result



        return "Không cần tool"



    # ---------------------
    # ReAct Loop
    # ---------------------

    def run(self, goal):


        print(
            f"\n🎯 Goal: {goal}"
        )


        # Thought

        print(
            "\n🧠 Thought:"
        )


        action = self.think(goal)


        print(
            f"Agent chọn tool: {action}"
        )



        # Action

        print(
            "\n🛠️ Action:"
        )


        observation = self.act(
            action
        )


        print(
            "\n👁️ Observation:"
        )

        print(
            observation
        )



        # Second Thought

        print(
            "\n🧠 Thought:"
        )


        answer = self.generate_answer(
            goal,
            observation
        )


        print(
            "\n🏁 Final Answer:"
        )


        print(answer)



        self.memory.append(
            {
                "goal": goal,
                "answer": answer
            }
        )



    # ---------------------
    # Final Response
    # ---------------------

    def generate_answer(
        self,
        goal,
        observation
    ):


        if isinstance(
            observation,
            dict
        ):


            weather = (
                f"{observation['temp']}, "
                f"{observation['condition']}, "
                f"độ ẩm {observation['humidity']}"
            )


            advice = clothing_advisor(
                weather
            )


            return (
                f"🌤 Thời tiết hiện tại: "
                f"{weather}. "
                f"{advice}"
            )


        else:

            return (
                f"Thông tin tìm được: "
                f"{observation}"
            )





# ==========================
# DEMO
# ==========================


if __name__ == "__main__":


    agent = ReactiveAgent()


    agent.run(
        "Thời tiết Hà Nội hôm nay thế nào và nên mặc gì?"
    )


    print("\n" + "="*60)


    agent.run(
        "Tìm vé máy bay Hà Nội đi Đà Nẵng"
    )