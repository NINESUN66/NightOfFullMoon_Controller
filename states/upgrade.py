from typing import TYPE_CHECKING, Set, List, Tuple, Union, Optional, Dict
import logging
import time
import cv2 # 确保导入 cv2
import numpy as np # 确保导入 numpy
from game_state import GameState
from .map_selection import MapSelectionState # 导入 MapSelectionState


# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 使用相对导入

logger = logging.getLogger(__name__)


class UpgradeState(GameState):
    """
    处理升级状态。
    """
    def handle(self):
        """
        处理升级状态。

        1.  **识别:** 检查是否在升级界面。
        2.  **决策:** 询问 LLM 选择哪个升级选项。
        3.  **定位:** 使用 OCR 找到 LLM 选择的选项文本的位置。
        4.  **执行:** 模拟点击找到的选项。
        5.  **转换:** 转换到下一个状态（通常是 `MapSelectionState`）。

        Returns:
            None
        """
        if not self.context:
            logger.error("UpgradeState 未设置上下文。")
            return
        logger.info(f"--- 处理 {type(self).__name__} ---")

        # 定义区域 (保持不变)
        text_region = (0.4, 0.24, 0.2, 0.06) # 升级界面标题区域 ("升级", "恭喜")
        reward_region = (0.26, 0.53, 0.47, 0.05) # 包含升级选项文本的区域

        # --- 1. 识别是否在升级界面 ---
        # 使用 recognize_text_in_relative_roi 获取文本
        title_text, _ = self.context.recognize_text_in_relative_roi(
            text_region,
            debug_filename="images/debug_upgrade_title.png" # 使用正斜杠或双反斜杠
        )

        if not title_text:
            logger.warning("  -> 未识别到升级界面标题区域的文本。可能不在升级界面。")
            from states.map_selection import MapSelectionState
            self.context.transition_to(MapSelectionState())
            time.sleep(1) # 短暂等待再次检查
            return

        logger.debug(f"  -> 识别到的标题区域文本: '{title_text}'")

        # 检查关键字判断是否在升级界面
        if "升级" in title_text or "恭喜" in title_text:
            logger.info("  -> 检测到升级界面。")

            # --- 2. 识别升级选项 ---
            options_text, _ = self.context.recognize_text_in_relative_roi(
                reward_region,
                debug_filename="images/debug_upgrade_options.png"
            )

            if not options_text:
                logger.warning("  -> 未识别到升级选项区域的文本。")
                click = self.context.get_input_simulator()
                click.click_relative(0.5, 0.5) # 点击屏幕中心，尝试直接跳过升级界面
                from states.map_selection import MapSelectionState
                self.context.transition_to(MapSelectionState())
                return

            logger.info(f"  -> 识别到的升级选项文本: '{options_text}'")

            # --- 3. 获取 Prompt 模板 ---
            prompt_key = "upgrade"
            template = self.context.get_prompt_template(prompt_key)
            if not template:
                logger.error(f"  -> 错误：找不到 Prompt 模板 '{prompt_key}'。无法进行决策。")
                time.sleep(1)
                return

            # --- 4. 构建 Prompt 并询问 LLM ---
            # 清理选项文本，去除多余空格和换行符，方便 LLM 处理
            cleaned_options = ' '.join(options_text.split())
            format_data = {"options_text": cleaned_options} # <--- 这里使用了 'upgrade_options'
            try:
                formatted_prompt = template.format(**format_data) # <--- 这里尝试用 format_data 填充模板
            except KeyError as e:
                logger.error(f"  -> 格式化 Prompt '{prompt_key}' 时出错：缺少键 {e}")
                time.sleep(1)
                return

            logger.info(f"  -> 询问 LLM 升级选择...")
            logger.debug(f"  -> Prompt: \"{formatted_prompt}\"")
            llm_decision = self.context.ask_llm(formatted_prompt, history_type='map') # 使用 map 历史

            # --- 5. 解析决策，定位并执行点击 ---
            if llm_decision:
                llm_decision = llm_decision.strip()
                logger.info(f"  -> LLM 决策：'{llm_decision}'")

                # --- 尝试用 OCR 定位 LLM 选择的文本 ---
                logger.info(f"  -> 尝试在奖励区域 {reward_region} 定位文本 '{llm_decision}'...")
                option_coords_in_roi = self.context.find_text_coordinates_in_relative_roi(
                    llm_decision,
                    reward_region,
                    debug_filename=f"images/debug_find_{llm_decision}.png"
                )

                if option_coords_in_roi:
                    rel_x_in_roi, rel_y_in_roi, rel_w_in_roi, rel_h_in_roi = option_coords_in_roi
                    logger.info(f"  -> OCR 成功定位到选项 '{llm_decision}' 在奖励区域内的相对坐标: x={rel_x_in_roi:.3f}, y={rel_y_in_roi:.3f}, w={rel_w_in_roi:.3f}, h={rel_h_in_roi:.3f}")

                    # 计算选项中心点在屏幕上的绝对相对坐标
                    reward_roi_left, reward_roi_top, reward_roi_width, reward_roi_height = reward_region
                    # 计算 ROI 内的相对中心点
                    center_x_in_roi = rel_x_in_roi + rel_w_in_roi / 2
                    center_y_in_roi = rel_y_in_roi + rel_h_in_roi / 2
                    # 转换为屏幕的相对坐标
                    click_x = reward_roi_left + center_x_in_roi * reward_roi_width
                    click_y = reward_roi_top + center_y_in_roi * reward_roi_height

                    logger.info(f"  -> 计算点击坐标 (屏幕相对): ({click_x:.3f}, {click_y:.3f})")

                    # --- 执行点击 ---
                    click = self.context.get_input_simulator()
                    if click:
                        click.click_relative(click_x, click_y)
                        logger.info(f"  -> 已点击选项 '{llm_decision}'。")
                        time.sleep(1.5) # 等待点击生效和界面过渡

                        # --- 转换状态 ---
                        # 点击升级选项后，通常返回地图
                        if "清除" in llm_decision:
                            logger.info("  -> 点击了清除选项，转换到 Tavern。")
                            from states.tavern import TavernState
                            self.context.transition_to(TavernState())
                        elif "强化" in llm_decision:
                            logger.info("  -> 点击了强化选项，转换到 Blacksmith。")
                            from states.black_smith import BlacksmithState
                            self.context.transition_to(BlacksmithState(from_upgrade_event=True))
                        else :
                            logger.info("  -> 点击了升级选项，转换到 MapSelectionState。")
                            from states.map_selection import MapSelectionState
                            self.context.transition_to(MapSelectionState())
                        return

                    else:
                        logger.error("  -> 无法获取 InputSimulator，无法点击选项。")
                        time.sleep(1)
                        return

                else:
                    logger.error(f"  -> OCR 未能在奖励区域 {reward_region} 中定位到 LLM 选择的文本 '{llm_decision}'。")
                    # 无法定位，可以选择等待或转回地图
                    logger.info("  -> 因无法定位选项，将等待后重试。")
                    time.sleep(1)
                    return

            else:
                logger.warning("  -> LLM 未能提供升级选择。")
                # LLM 无响应，可以选择等待或转回地图
                logger.info("  -> 因 LLM 无响应，将等待后重试。")
                time.sleep(1)
                return
        else:
            logger.warning(f"  -> 标题区域文本 '{title_text}' 不包含 '升级' 或 '恭喜'。可能不在升级界面。")
            # 确认不在升级界面，可以转换回地图
            from states.map_selection import MapSelectionState
            self.context.transition_to(MapSelectionState())
            time.sleep(1) # 短暂等待再次检查
            return
