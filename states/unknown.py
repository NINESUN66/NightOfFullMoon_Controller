from typing import TYPE_CHECKING, Set, List, Tuple, Union, Optional, Dict
import logging
import time
from game_state import GameState


# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 使用相对导入
    
logger = logging.getLogger(__name__)

class UnknownState(GameState):
    """
    处理无法识别当前游戏状态的情况。
    """
    def handle(self):
        """
        尝试重新识别状态或执行通用检查。

        1.  **识别:** 尝试更通用的识别方法，检查是否在地图、战斗、主菜单等常见界面。检查是否有模态弹窗（如设置、退出确认）。
        2.  **决策:** 根据识别结果决定下一步操作。可能是关闭弹窗，或者强制转换到一个最可能的状态（如 `MapSelectionState`）。
        3.  **执行:** 模拟点击关闭按钮等。
        4.  **转换:** 转换到识别出的状态，或者如果仍然无法识别，可能保持在 `UnknownState` 并记录错误，或转换到特定的错误处理状态。

        Returns:
            None
        """
        if not self.context:
            logger.error("UnknownState 未设置上下文。")
            return
        logger.warning(f"正在处理 {type(self).__name__}...") # 对未知状态使用警告级别

        # --- 尝试识别 ---
        # 1. 获取截图和数据
        screenshot = self.context.get_screenshot()
        game_data = self.context.get_game_data()
        ocr_sample = "N/A"
        if screenshot:
            # 尝试 OCR 屏幕中央区域获取线索
            center_coords = (0.4, 0.4, 0.2, 0.2)
            ocr_sample = self.context.recognize_text_in_relative_roi(center_coords) or "N/A"
        from .map_selection import MapSelectionState
        # 2. 构建 Prompt 给 LLM
        prompt_key = "unknown_state"
        template = self.context.get_prompt_template(prompt_key)
        if not template:
            logger.error(f"  -> 错误：找不到 Prompt 模板 '{prompt_key}'。尝试默认恢复。")
            # 默认尝试返回地图
            self.context.transition_to(MapSelectionState())
            return

        format_data = {
            "ocr_sample": ocr_sample,
            "game_data_summary": str(game_data) if game_data else "无数据"
        }
        try:
            formatted_prompt = template.format(**format_data)
        except KeyError as e:
            logger.error(f"  -> 格式化 Prompt '{prompt_key}' 时出错：缺少键 {e}。尝试默认恢复。")
            self.context.transition_to(MapSelectionState())
            return

        logger.info(f"  -> 询问 LLM 识别未知状态：\"{formatted_prompt}\"")
        llm_decision = self.context.ask_llm(formatted_prompt, history_type='map') # 使用 map 历史

        if llm_decision:
            logger.info(f"  -> LLM 对未知状态的分析：'{llm_decision}'")
            # TODO: 解析 LLM 的响应，尝试转换到建议的状态或执行建议的操作
            # suggested_state, suggested_action = parse_unknown_state_decision(llm_decision)
            # if suggested_state == "Map":
            #    self.context.transition_to(MapSelectionState())
            # elif suggested_state == "Combat":
            #    self.context.transition_to(CombatState())
            # ...
            # elif suggested_action == "Close Popup":
            #    find_and_click_close_button()
            # else:
            #    logger.warning("  -> LLM 建议不可操作或无法识别。重试 MapSelectionState。")
            #    self.context.transition_to(MapSelectionState()) # 默认尝试地图
        else:
            logger.warning("  -> LLM 未能分析未知状态。尝试默认恢复 (MapSelectionState)。")
            self.context.transition_to(MapSelectionState()) # 默认尝试地图

