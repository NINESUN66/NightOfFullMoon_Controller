from typing import TYPE_CHECKING, Set, List, Tuple, Union, Optional, Dict
import logging
import time
from game_state import GameState
from .map_selection import MapSelectionState

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 使用相对导入
    
logger = logging.getLogger(__name__)

class FairyBlessingState(GameState):
    """
    处理仙女祝福事件的状态。
    """
    def handle(self):
        """
        选择仙女祝福。

        1.  **识别:** 识别屏幕上提供的祝福选项文本。
        2.  **决策:** 将祝福选项发送给 LLM，询问选择哪个。
        3.  **执行:** 模拟点击 LLM 选择的祝福选项及确认按钮。
        4.  **转换:** 完成选择后，转换回 `MapSelectionState`。

        Returns:
            None
        """
        if not self.context:
            logger.error("FairyBlessingState 未设置上下文。")
            return
        logger.info(f"正在处理 {type(self).__name__}...")
        # 定义祝福选项区域的相对坐标
        blessing_coords = (0.28, 0.55, 0.50, 0.07) # (left, top, width, height)
        # 定义 LLM 的 Prompt 模板键
        prompt_key = "fairy_blessing"
        template = self.context.get_prompt_template(prompt_key)
        if not template:
            logger.error(f"  -> 错误：找不到 Prompt 模板 '{prompt_key}'。")
            return
        # 定义调试文件名
        debug_filename = "images/debug_fairy_blessing_region.png" # 修改文件名以区分

        # 调用 GameContext 的辅助方法
        recognized_text, llm_decision = self.context.recognize_text_in_relative_roi_and_ask_llm(
            relative_coords=blessing_coords,
            prompt_template=template,
            knowledge_category="blessings",
            debug_filename=debug_filename
        )

        # 处理结果
        if recognized_text is None:
            logger.warning("  -> 未能识别仙女祝福区域。")
            # 可以添加错误处理逻辑
            # self.context.transition_to(UnknownState())
            return
        if llm_decision is None:
            logger.warning("  -> LLM 决策失败或被跳过，无法继续。")
            # 可以添加错误处理逻辑
            return

        # --- 后续逻辑 ---
        logger.info(f"  -> 最终祝福文本 (OCR)：'{recognized_text}'")
        logger.info(f"  -> 最终 LLM 决策：'{llm_decision}'")

        click_regions = [
            (0.3,0.5), # 第一个
            (0.5,0.5), # 第二个
            (0.7,0.5), # 第三个
            (0.5,0.7) # 确定按钮
        ]

        # 根据LLM结果点击
        try:
            click = self.context.get_input_simulator()
            selected_region_index = int(llm_decision) - 1
            if 0 <= selected_region_index < len(click_regions) -1: # 确保索引有效且不是确定按钮
                selected_region = click_regions[selected_region_index]
                click.click_relative(*selected_region) # 使用 * 解包元组
                logger.info(f"  -> 点击祝福选项：{selected_region}")
            else:
                logger.error(f"  -> 错误：LLM 决策 '{llm_decision}' 对应的索引 {selected_region_index} 无效或指向确定按钮。")
                return

        except ValueError:
            logger.error(f"  -> 错误：无法将 LLM 决策 '{llm_decision}' 转换为整数。")
            return
        except Exception as e:
            logger.error(f"  -> 错误：点击祝福选项时发生异常：{e}", exc_info=True)
            return

        # 点击确定按钮
        confirm_button_region = click_regions[3]
        click.click_relative(*confirm_button_region) # 使用 * 解包元组
        logger.info(f"  -> 点击确定按钮：{confirm_button_region}")

        # --- 转换 ---
        next_state = MapSelectionState()
        self.context.transition_to(next_state)
        logger.info("  -> 转换回 MapSelectionState。")