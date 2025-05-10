import os
from typing import Optional
import openai # Example: If using OpenAI
# from google.generativeai import GenerativeModel # Example: If using Gemini
import requests # Example: If using a custom API endpoint
from typing import Optional, List, Dict
import logging
logger = logging.getLogger(__name__)

class LLMClient:
    """
    一个与大型语言模型 (LLM) 交互的客户端。
    负责将文本提示发送给 LLM 并获取生成的响应。
    注意：这是一个基本实现，你需要根据你选择的 LLM 服务（如 OpenAI, Gemini, Azure OpenAI, 或本地模型）
          来填充实际的 API 调用逻辑。
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.0-flash-exp"):
        """
        初始化 LLM 客户端。

        Args:
            api_key (Optional[str]): 用于访问 LLM 服务的 API 密钥。
                                     在实际应用中，建议从环境变量或安全配置中读取。
            model_name (str): 要使用的 LLM 模型名称。
        """
        # 在实际应用中，请使用更安全的方式管理 API 密钥，例如环境变量
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model_name
        self.client = None # Initialize client as None

        # Only initialize if API key is available or using a mock model
        if self.api_key or model_name == "local-mock":
            try:
                # Example for OpenAI compatible API
                self.client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url="https://api.chatanywhere.tech/v1", # 替换为实际的 API 基础 URL
                )
                logger.info(f"LLMClient 已为模型初始化: {self.model_name}")
            except Exception as e:
                 logger.error(f"初始化 OpenAI 客户端失败: {e}", exc_info=True)
                 self.client = None # Ensure client is None on failure
        else:
            logger.warning("未提供 LLM_API_KEY 或在环境变量中未找到。LLM 客户端未初始化。")


    def generate(self, prompt: str, history: Optional[List[Dict[str, str]]] = None, max_tokens: int = 150) -> Optional[str]:
        """
        向 LLM 发送提示（和历史记录）并获取生成的文本响应。

        Args:
            prompt (str): 当前的用户提示。
            history (Optional[List[Dict[str, str]]]): 可选的聊天历史记录列表。
                每个字典应包含 "role" ("user" 或 "assistant") 和 "content"。
            max_tokens (int): 控制生成响应的最大长度（token 数）。

        Returns:
            Optional[str]: LLM 生成的文本响应。如果发生错误或无法获取响应，则返回 None。
        """
        logger.info(f"\n--- 向 LLM ({self.model_name}) 发送提示 ---")
        messages_log = [] # For logging purposes
        if history:
            logger.debug("--- 历史记录 ---")
            for msg in history:
                log_content = msg['content'][:100] + ('...' if len(msg['content']) > 100 else '')
                logger.debug(f"{msg['role']}: {log_content}") # 打印部分历史内容
                messages_log.append(f"{msg['role']}: {log_content}")
            logger.debug("--- 结束历史记录 ---")
        logger.info(f"用户: {prompt}")
        messages_log.append(f"用户: {prompt}")
        logger.info("--- 结束提示 ---")

        llm_response = None
        messages = []

        # 构建发送给 API 的消息列表
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        try:
            # --- 使用 OpenAI 兼容的 API ---
            # 检查 self.client 是否已成功初始化
            if self.client and (self.model_name.startswith("gpt") or self.model_name.startswith("gemini")): # 假设 gemini 也通过 OpenAI 兼容接口访问
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages, # 传递包含历史记录的消息列表
                    max_tokens=max_tokens,
                    temperature=0.7,
                )
                if response and response.choices and len(response.choices) > 0:
                    message = response.choices[0].message
                    if message and message.content:
                        llm_response = message.content.strip()
                    else:
                        logger.warning("LLM 响应信息为空")
                        llm_response = None

            elif self.model_name == "local-mock":
                 logger.info("使用本地模拟响应。")
                 # Simulate a response based on the prompt
                 if "map" in prompt.lower():
                     llm_response = "Choose: Shop"
                 elif "combat" in prompt.lower():
                     llm_response = "Play: Defend (1)"
                 elif "shop" in prompt.lower():
                     llm_response = "Buy: Health Potion (50g)"
                 else:
                     llm_response = "模拟响应：操作成功。" # Mock response: Action successful.
            else:
                logger.warning(f"LLM 客户端未初始化或不支持模型 '{self.model_name}'。")
                # 可以选择返回一个错误信息或 None
                llm_response = None # 或者 "错误：LLM 未配置"

            # ------------------------------------------------------------------

            if llm_response:
                logger.info(f"--- LLM 响应 --- \n{llm_response}\n--- 结束 LLM 响应 ---")
            else:
                logger.info("--- LLM 响应: 无 ---")

            return llm_response

        except openai.AuthenticationError as e:
            logger.error(f"LLM 身份验证错误: {e}。请检查您的 API 密钥和基础 URL。", exc_info=True)
            return None
        except openai.RateLimitError as e:
            logger.error(f"LLM 速率限制错误: {e}。请稍后重试。", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"与 LLM 交互时发生意外错误: {e}", exc_info=True)
            return None


# --- 使用示例 ---
if __name__ == "__main__":
    # Configure basic logging for the test block
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    # 使用模拟响应进行测试 (不需要 API Key)
    # llm_client = LLMClient(model_name="local-mock")

    # 如果你有 API Key (例如放在环境变量 LLM_API_KEY 中) 并想测试真实模型:
    llm_client = LLMClient(model_name="gpt-3.5-turbo") # 替换成你想用的模型

    # 为了演示，我们强制使用模拟客户端
    # logger.info("--- 使用模拟响应测试 LLMClient ---")
    # llm_client = LLMClient(model_name="local-mock") # Use mock for testing

    # 模拟地图选择
    map_prompt = """
当前地图节点:
1. 战斗 (精英)
2. 商店
3. 未知事件 (?)

我应该选择哪个节点？请考虑风险和回报。
"""
    map_choice = llm_client.generate(map_prompt)
    logger.info(f"LLM 建议的地图选择: {map_choice}")

    logger.info("-" * 20)

    # 模拟战斗决策
    combat_prompt = """
玩家 HP: 50/80, 能量: 3/3
手牌: [打击 (1), 防御 (1), 重击 (2)]
敌人: Louse (HP: 12/12, 意图: 攻击 6)

我应该打出哪张牌？还是结束回合？
"""
    combat_action = llm_client.generate(combat_prompt)
    logger.info(f"LLM 建议的战斗行动: {combat_action}")

    logger.info("-" * 20)

    # 模拟商店决策
    shop_prompt = """
玩家金币: 150
商店物品:
- 生命药水 (50g)
- 火焰药水 (75g)
- 卡牌移除服务 (100g)
- 卡牌: 晾衣绳 (120g)

我应该购买什么或做什么？
"""
    shop_action = llm_client.generate(shop_prompt)
    logger.info(f"LLM 建议的商店行动: {shop_action}")