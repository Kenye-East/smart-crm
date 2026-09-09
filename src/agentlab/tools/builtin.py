"""内置示例工具"""

from .base import tool


@tool(
    name="calculator",
    description="计算数学表达式，支持基本运算",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "数学表达式，如 '2 + 3 * 4'",
            }
        },
        "required": ["expression"],
    },
)
def CalculatorTool(expression: str) -> str:
    """计算器工具"""
    try:
        # 安全地计算表达式
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return f"错误：包含非法字符"
        result = eval(expression)  # 注意：生产环境需要更安全的实现
        return str(result)
    except Exception as e:
        return f"计算错误：{e}"


@tool(
    name="get_weather",
    description="获取指定城市的天气信息",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，如 '北京'",
            }
        },
        "required": ["city"],
    },
)
def WeatherTool(city: str) -> str:
    """天气查询工具（模拟数据）"""
    # 模拟天气数据
    weather_data = {
        "北京": "晴天，气温 25°C，湿度 40%",
        "上海": "多云，气温 28°C，湿度 65%",
        "广州": "小雨，气温 30°C，湿度 80%",
        "深圳": "阴天，气温 27°C，湿度 70%",
    }
    return weather_data.get(city, f"{city}：暂无天气数据")
