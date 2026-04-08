import yaml
from pathlib import Path
from .llm import LLMClient

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    """加载配置文件"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class DietExtractor:
    """饮食描述提取器，使用LLM从自然语言描述中提取结构化信息"""
    
    def __init__(self, config: dict):
        self.meal_types = config.get("diet", {}).get("meal_types", ["早餐", "午餐", "晚餐", "零食", "其他"])
        self.threshold: float = config.get("diet", {}).get("confidence_threshold", 0.7)
        self._llm = LLMClient(config.get("llm", {}))
    
    def extract(self, description: str) -> dict:
        """
        从饮食描述中提取结构化信息
        
        返回结果：
        {
            "status": "confirmed" | "low_confidence" | "error",
            "meal_type": str,      # 餐顿类型：早餐/午餐/晚餐/零食/其他
            "food_name": str,      # 主要食物名称
            "quantity": str,       # 份量描述
            "confidence": float,   # 置信度
            "reasoning": str,      # 提取理由
            "error": bool          # 是否出错
        }
        """
        try:
            result = self._llm.extract_diet_info(description, self.meal_types)
            
            if result.get("error"):
                return {**result, "status": "error"}
            
            confidence = result.get("confidence", 0.0)
            
            if confidence < self.threshold:
                status = "low_confidence"
            else:
                status = "confirmed"
            
            return {**result, "status": status}
            
        except Exception as e:
            return {
                "status": "error",
                "meal_type": "其他",
                "food_name": description,
                "quantity": "",
                "confidence": 0.0,
                "reasoning": f"提取失败: {str(e)}",
                "error": True
            }