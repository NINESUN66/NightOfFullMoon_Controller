from typing import TYPE_CHECKING, Set, List, Tuple, Union, Optional, Dict
import logging
import time
from game_state import GameState

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 使用相对导入
    
logger = logging.getLogger(__name__)

class ChestState(GameState):
    """
    处理打开宝箱事件的状态。
    """
    def handle(self):
        """
        打开宝箱并决定是否拾取奖励。

        1.  **识别:** 屏幕上可能只有一个“打开”按钮，点击后识别出现的奖励卡牌或物品。
        2.  **决策:** 将奖励信息发送给 LLM，询问是否拾取。
        3.  **执行:** 根据 LLM 决策模拟点击“拾取”或“跳过”按钮。
        4.  **转换:** 完成操作后，转换回 `MapSelectionState`。

        Returns:
            None
        """
        if not self.context:
            logger.error("ChestState 未设置上下文。")
            return
        logger.info(f"正在处理 {type(self).__name__}...")

        # 识别奖励内容
        reward_coords = (0.4, 0.1, 0.2, 0.05) # (left, top, width, height)
        prompt_key = "chest_reward"
        template = self.context.get_prompt_template(prompt_key)
        if not template:
            logger.error(f"  -> 错误：找不到 Prompt 模板 '{prompt_key}'。")
            return
        debug_filename = "images/debug_chest_reward_region.png"

        recognized_text, llm_decision = self.context.recognize_text_in_relative_roi_and_ask_llm(
            relative_coords=reward_coords,
            prompt_template=template,
            knowledge_category="cards",
            debug_filename=debug_filename
        )

        if recognized_text is None:
            logger.warning("  -> 未能识别宝箱奖励区域。")
            return
        if llm_decision is None:
            logger.warning("  -> LLM 决策失败或被跳过，无法继续。")
            return

        logger.info(f"  -> 最终奖励文本 (OCR)：'{recognized_text}'")
        logger.info(f"  -> 最终 LLM 决策：'{llm_decision}'")

        # 获取模拟点击
        click = self.context.get_input_simulator()
        from .map_selection import MapSelectionState
        try:
            if "拿取" in llm_decision:
                logger.info("  -> LLM 决定拿取奖励。")
                click.click_relative(0.45, 0.8)
                logger.info("  -> 点击拾取按钮。")
            elif "跳过" in llm_decision:
                logger.info("  -> LLM 决定跳过奖励。")
                click.click_relative(0.55, 0.8)
                logger.info("  -> 点击跳过按钮。")
                # 跳过后需要将该关卡删除
                last_node_info = self.context.get_last_selected_node() # 从 Context 获取节点信息
                if last_node_info:
                    logger.info(f"  -> 尝试删除节点：{last_node_info}")
                    try:
                        # 使用正确的键 'index' 获取关卡编号
                        level_index = last_node_info['index']
                        click.delete_level(level_index) # 调用 delete_level
                        logger.info("  -> 已调用删除节点方法。")
                        time.sleep(1.0) # 等待地图更新
                    except KeyError:
                         logger.error(f"  -> 错误：'last_node_info' 字典中缺少 'index' 键。信息: {last_node_info}")
                    except Exception as e_del:
                         logger.error(f"  -> 调用 delete_level 时出错: {e_del}", exc_info=True)
                else:
                    logger.warning("  -> 无法获取上一个节点信息，无法删除关卡。")
            else:
                logger.warning(f"  -> 无法识别的 LLM 决策格式：{llm_decision}")
                next_state = MapSelectionState()
                self.context.transition_to(next_state)
                return
        except Exception as e:
            logger.error(f"  -> 错误：处理开启宝箱的 LLM 决策时发生异常：{e}", exc_info=True)
            next_state = MapSelectionState()
            self.context.transition_to(next_state)
            return

        # --- 转换 ---
        next_state = MapSelectionState()
        self.context.transition_to(next_state)
        logger.info("  -> 转换回 MapSelectionState。")

