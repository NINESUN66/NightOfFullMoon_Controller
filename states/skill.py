from typing import TYPE_CHECKING, Set, List, Tuple, Union, Optional, Dict
import logging
import time
from game_state import GameState
from .map_selection import MapSelectionState
from .chest import ChestState

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 使用相对导入
    
logger = logging.getLogger(__name__)


class SkillAvailableState(GameState):
    """
    处理技能可用状态。 (这个状态可能需要重新评估，是否真的需要独立状态)
    """
    def handle(self):
        """
        处理技能可用状态。 (逻辑可能需要调整)

        1.  **识别:** 检查技能是否可用。
        2.  **执行:** 模拟点击技能按钮。
        3.  **转换:** 转换回 `MapSelectionState` 状态。

        Returns:
            None
        """
        if not self.context:
            logger.error("SkillAvailableState 未设置上下文。")
            return
        logger.info(f"正在处理 {type(self).__name__}...")

        click = self.context.get_input_simulator()
        click.click_relative(0.21, 0.9)
        click.click_relative(0.21, 0.9)
        click.click_relative(0.21, 0.9)
        click.click_relative(0.21, 0.9)

        logger.info("  -> 点击技能按钮。")

        # 识别提示区域是否有提示 (这个逻辑可能不可靠)
        tip_coords = (0.4, 0.24, 0.25, 0.05) # (left, top, width, height)
        debug_filename = "images/debug_skill_tip_region.png"
        logger.info(f"  -> 识别技能提示区域文本：{tip_coords}")
        recognized_text = self.context.recognize_text_in_relative_roi(
            relative_coords=tip_coords,
            debug_filename=debug_filename
        )

        if recognized_text and "战斗后才可以使用" in recognized_text:
            logger.warning(f"  -> 检测到技能提示：'{recognized_text}'。假设技能现在不可用。")
            
        else :
            logger.info(f"  -> 未检测到禁止性技能提示（文本：'{recognized_text}'）。假设技能已使用或已执行操作。")
            next_state = ChestState()
            self.context.transition_to(next_state)
            logger.info("  -> 转换到 ChestState。")
            return

        next_state = MapSelectionState()
        self.context.transition_to(next_state)
        logger.info("  -> 转换回 MapSelectionState。")

