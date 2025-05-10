from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional
import logging # 导入 logging

logger = logging.getLogger(__name__) # 获取 logger 实例

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 仅在类型检查时导入

class GameState(ABC):
    """
    抽象状态基类，定义所有具体游戏状态必须实现的接口。
    """

    def __init__(self):
        """初始化状态基类。"""
        # 每个状态实例都需要能够访问 GameContext 以获取资源和进行状态转换。
        # 这个引用通常由 GameContext 在创建状态实例或转换到该状态时设置。
        self.context: Optional['GameContext'] = None

    @abstractmethod
    def handle(self):
        """
        处理当前状态的核心逻辑。子类必须实现此方法。

        此方法通常包含以下步骤：
        1.  **识别 (Recognition):** 使用 `self.context` 提供的工具（如 `get_screenshot`, `get_game_data`, `get_ocr_engine`）
            来分析当前游戏画面或数据，识别出关键信息（例如：按钮位置、文本内容、玩家/敌人状态、可用选项等）。
        2.  **决策 (Decision):** 根据识别到的信息，决定下一步的操作。
            - 对于简单逻辑，可以直接判断（例如：如果看到“胜利”字样，则转换到奖励状态）。
            - 对于复杂逻辑，可以将信息构建成 Prompt，调用 `self.context.ask_llm()` 让 LLM 做出决策。
        3.  **执行 (Execution):** 根据决策执行相应的游戏内操作。这可能需要调用一个模拟输入库（未在此定义）
            来模拟鼠标点击、键盘输入等。例如：点击 LLM 建议购买的商品按钮。
        4.  **转换 (Transition):** 根据执行结果或识别到的新情况，创建一个新的状态对象，
            并调用 `self.context.transition_to(new_state)` 来切换到下一个状态。
            例如：点击“进入战斗”按钮后，转换到 `CombatState`。

        Args:
            (隐式) self: 状态对象本身，可以通过 self.context 访问 GameContext。

        Returns:
            None. 状态的改变通过调用 self.context.transition_to() 实现。
        """
        raise NotImplementedError("子类必须实现 'handle' 方法。") # 修改了错误信息为中文

# --- 示例具体状态 (仅用于演示，说明如何使用) ---
# class ExampleConcreteState(GameState):
#     def handle(self):
#         if not self.context:
#             logger.error("错误：此状态未设置上下文。") # 使用 logger.error 并改为中文
#             return
#
#         logger.info(f"正在处理 {type(self).__name__}...") # 使用 logger.info 并改为中文
#
#         # 1. 识别
#         # screenshot = self.context.get_screenshot()
#         # game_data = self.context.get_game_data()
#         # ocr_results = self.context.ocr_region(...) # 假设有这个方法
#         logger.info("  - 识别阶段：分析屏幕/数据...") # 使用 logger.info 并改为中文
#
#         # 2. 决策
#         # decision = self.context.ask_llm("我应该采取什么行动？") # 假设 LLM 问题也需要翻译
#         decision = "默认操作" # 示例决策也改为中文
#         logger.info(f"  - 决策阶段：决定执行 '{decision}'。") # 使用 logger.info 并改为中文
#
#         # 3. 执行
#         # simulate_click(x, y)
#         logger.info(f"  - 执行阶段：正在执行 '{decision}'...") # 使用 logger.info 并改为中文
#
#         # 4. 转换
#         # from next_state import NextState # 导入下一个状态类
#         # next_state_instance = NextState()
#         # self.context.transition_to(next_state_instance)
#         logger.info("  - 转换阶段：转换到下一个状态（模拟）。") # 使用 logger.info 并改为中文