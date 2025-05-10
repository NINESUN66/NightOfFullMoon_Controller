from typing import TYPE_CHECKING, Set, List, Tuple, Union, Optional, Dict
import logging
import time
import os
import sys

from game_state import GameState

from .map_selection import MapSelectionState
from .tavern import TavernState
from .chest import ChestState
from .fairy_blessing import FairyBlessingState
from .black_smith import BlacksmithState
from .combat import CombatState
from .shop import ShopState
from .dialogue import DialogueRewardState
from .unknown import UnknownState
from .skill import SkillAvailableState
from .upgrade import UpgradeState

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from ..game_context import GameContext # 使用相对导入

logger = logging.getLogger(__name__)

class InitializationState(GameState):
    """
    处理游戏启动和进入冒险模式的状态。
    """
    def handle(self):
        """
        执行初始化逻辑。

        1.  **识别:** 检查游戏是否已启动，是否在主菜单。
        2.  **决策:** 决定点击“开始冒险”或类似按钮。
        3.  **执行:** 模拟点击进入冒险模式。
        4.  **转换:** 成功进入地图后，转换到 `MapSelectionState`。

        Returns:
            None
        """
        if not self.context:
            logger.error("InitializationState 未设置上下文。")
            return
        logger.info(f"正在处理 {type(self).__name__}...")
        # 目前实现策略是人工点击“开始冒险”按钮
        next_state = MapSelectionState() # 初始为地图选择状态
        # next_state = FairyBlessingState() # 初始为仙女祝福状态
        # next_state = CombatState() # 初始为战斗状态
        # next_state = ShopState() # 初始为商店状态
        # next_state = TavernState() # 初始为酒馆状态
        # next_state = BlacksmithState() # 初始为铁匠铺状态
        # next_state = ChestState() # 初始为宝箱状态
        # next_state = DialogueRewardState() # 初始为对话奖励状态
        # next_state = SkillAvailableState() # 初始为技能可用状态
        # next_state = UpgradeState() # 初始为升级状态
        self.context.transition_to(next_state)
        logger.info("转换到下一个状态（目前为手动选择）。")