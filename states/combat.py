from typing import TYPE_CHECKING, List, Dict, Tuple, Union, Optional
import logging
import time
import re # 导入正则表达式库用于解析卡牌费用

from game_state import GameState
from .map_selection import MapSelectionState

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 使用相对导入

logger = logging.getLogger(__name__)

# --- 定义常量 ROI ---
PLAYER_HP_ROI = (0.45, 0.95, 0.1, 0.04) # 用于可能的 OCR 补充，主要依赖内存
ENEMY_HP_ROI = (0.4, 0.35, 0.2, 0.05) # 用于可能的 OCR 补充，主要依赖内存
CARD_DRAG_TARGET_Y = 0.5 # 向上拖动到的屏幕中心 Y 坐标
# --- 胜利后检查区域 ---
DIALOGUE_INDICATOR_ROI = (0.53, 0.07, 0.2, 0.13)
UPGRADE_INDICATOR_ROI = (0.4, 0.24, 0.2, 0.06)
# --- 失败后按钮区域 ---
RETRY_BUTTON_ROI = (0.52, 0.76, 0.15, 0.05) # 失败后点击返回首页
OPEN_STORY_BUTTON_ROI = (0.87, 0.38, 0.08, 0.04) # 失败后点击打开故事
END_TURN_BUTTON_ROI = (0.78, 0.86, 0.1, 0.06) # 结束回合按钮区域
HAND_TEXT_ROI = (0.10, 0.6, 0.80, 0.07) # 手牌名区域

PLAYER_TURN_CHECK_POINT = (0.8, 0.87)  # 回合结束按钮上的固定检查点 (x, y)
PLAYER_TURN_COLOR_BGR = (52, 102, 79)  # 玩家回合时检查点的 BGR 颜色
ENEMY_TURN_COLOR_BGR = (89, 89, 89)    # 非玩家回合时检查点的 BGR 颜色
COLOR_TOLERANCE = 15                   # 颜色比较容差

DISCARD_PROMPT_ROI = (0.4, 0.15, 0.2, 0.1) # 弃牌提示文字区域 (同 _check_discard 中的 tip_roi)
DISCARD_CARD_NAME_ROI = (0.05, 0.33, 0.9, 0.05) # 弃牌选择界面卡牌名称大致区域 (y 轴和高度可能需要微调)
CONFIRM_DISCARD_BUTTON_ROI = (0.38, 0.8, 0.07, 0.05) # 弃牌界面的 "确定" 按钮
CANCEL_DISCARD_BUTTON_ROI = (0.55, 0.8, 0.07, 0.05) # 弃牌界面的 "取消" 按钮

class CombatState(GameState):
    """
    处理战斗场景的状态（优化版）。
    """
    def _is_color_close(self, color1: Optional[Tuple[int, int, int]], color2: Tuple[int, int, int], tolerance: int) -> bool:
        """检查两个 BGR 颜色是否在容差范围内接近"""
        if color1 is None:
            return False
        return all(abs(c1 - c2) <= tolerance for c1, c2 in zip(color1, color2))

    def _recognize_hand(self) -> List[Dict]:
        """
        识别手牌信息 (新方法：OCR 红框区域并解析)。
        识别红框区域内的文本，中文认为是卡牌名，数字认为是前一张卡牌的费用。
        """
        if not self.context: return []
        hand_cards = []
        logger.info("  -> 开始识别手牌 (红框 OCR 法)...")

        # 1. 对红框区域进行 OCR，获取带索引的文本块数组
        # 返回值是 List[Tuple[int, str]]
        _, recognized_blocks = self.context.recognize_text_in_relative_roi(
            HAND_TEXT_ROI,
            "images/debug_hand_text_area.png" # 使用正斜杠或双反斜杠
        )

        if not recognized_blocks:
            logger.warning("  -> 手牌区域 OCR 未返回任何文本块。")
            return []

        logger.debug(f"  -> 手牌区域 OCR 原始结果: {recognized_blocks}")

        # 2. 解析文本块，尝试匹配卡牌名和费用
        current_card_name = None
        # 按索引排序（虽然返回时应该已经有序，但以防万一）
        recognized_blocks.sort(key=lambda block: block[0])

        card_index_counter = 0 # 用于给手牌分配索引

        for block in recognized_blocks:
            # block 是 (index, text)
            text = block[1].strip() # <--- 修复：使用 block[1] 获取文本
            # coords = block[1] # <--- 移除：block[1] 不是坐标

            if not text:
                continue

            # 尝试判断是中文名还是数字费用
            is_chinese_name = bool(re.search(r'[\u4e00-\u9fff]', text))
            is_numeric_cost = text.isdigit()

            if is_chinese_name:
                # 如果之前有未匹配费用的卡牌名，记录下来（假设费用为0）
                if current_card_name:
                    logger.warning(f"  -> 卡牌 '{current_card_name}' 后面直接跟了另一个中文名 '{text}'，未找到费用，假设为0。")
                    # estimated_roi = current_card_coords if current_card_coords else (0,0,0,0) # <--- 移除 ROI
                    hand_cards.append({"name": current_card_name, "cost": 0, "index": card_index_counter}) # <--- 添加 index
                    card_index_counter += 1

                # 记录新的卡牌名，等待费用
                current_card_name = text
                # current_card_coords = coords # <--- 移除
                logger.debug(f"    识别到可能的卡牌名: '{current_card_name}'") # 移除坐标信息

            elif is_numeric_cost and current_card_name:
                # 如果当前有等待费用的卡牌名，并且识别到数字
                try:
                    cost = int(text)
                    if 0 <= cost <= 10: # 合理费用范围
                        logger.debug(f"    识别到卡牌 '{current_card_name}' 的费用: {cost}") # 移除坐标信息
                        # estimated_roi = current_card_coords if current_card_coords else coords # <--- 移除 ROI
                        hand_cards.append({"name": current_card_name, "cost": cost, "index": card_index_counter}) # <--- 添加 index
                        card_index_counter += 1
                        current_card_name = None # 重置，等待下一个卡牌名
                        # current_card_coords = None # <--- 移除
                    else:
                        logger.warning(f"  -> 识别到数字 '{text}'，但在卡牌 '{current_card_name}' 后面，且不在合理费用范围 (0-10)，忽略。") # 移除坐标信息
                except ValueError:
                    pass # 不应发生
            elif is_numeric_cost and not current_card_name:
                 logger.warning(f"  -> 识别到数字 '{text}'，但前面没有等待费用的卡牌名，忽略。") # 移除坐标信息
            # else:
            #      logger.debug(f"    忽略非中文非数字文本块: '{text}'") # 移除坐标信息


        # 处理最后一个可能没有匹配到费用的卡牌名
        if current_card_name:
            logger.warning(f"  -> 最后一个卡牌 '{current_card_name}' 未找到匹配的费用，假设为0。")
            # estimated_roi = current_card_coords if current_card_coords else (0,0,0,0) # <--- 移除 ROI
            hand_cards.append({"name": current_card_name, "cost": 0, "index": card_index_counter}) # <--- 添加 index
            card_index_counter += 1

        logger.info(f"  -> 手牌识别完成 (红框 OCR 法)，共 {len(hand_cards)} 张: {[(card['name'], card['cost']) for card in hand_cards]}")
        return hand_cards

    def _find_card_in_hand(self, card_name_to_find: str, hand_cards: List[Dict]) -> Optional[Dict]:
        """在手牌中查找卡牌 (模糊匹配) - 保持不变"""
        if not card_name_to_find: return None
        card_name_to_find = card_name_to_find.strip()

        # 优先精确匹配
        for card in hand_cards:
            if card_name_to_find == card['name']:
                logger.info(f"  -> 精确匹配到卡牌: '{card['name']}'")
                return card

        # 模糊匹配 (包含关系) - 目标名称包含在识别名称中
        for card in hand_cards:
            # 避免误匹配，例如 "打击" 匹配 "双重打击"
            # 可以增加长度判断或更复杂的匹配逻辑，这里暂时保持简单包含
            if card_name_to_find in card['name']:
                logger.info(f"  -> 模糊匹配 (目标 in 识别): '{card['name']}' (目标: '{card_name_to_find}')")
                return card

        # 模糊匹配 (包含关系) - 识别名称包含在目标名称中 (处理OCR识别不全的情况)
        for card in hand_cards:
             if card['name'] in card_name_to_find:
                logger.info(f"  -> 模糊匹配 (识别 in 目标): '{card['name']}' (目标: '{card_name_to_find}')")
                return card

        # 更宽松的模糊匹配 (去除空格和小写比较)
        target_norm = card_name_to_find.replace(" ", "").lower()
        for card in hand_cards:
            card_norm = card['name'].replace(" ", "").lower()
            # 简单包含或被包含
            if target_norm in card_norm or card_norm in target_norm:
                logger.info(f"  -> 宽松模糊匹配到卡牌: '{card['name']}' (目标: '{card_name_to_find}')")
                return card
        logger.warning(f"  -> 未能在手牌中找到卡牌: '{card_name_to_find}'")
        return None

    def _parse_discard_count(self) -> int:
        """从弃牌提示文本中解析需要丢弃的卡牌数量。"""
        if not self.context: return 0
        logger.info("  -> 识别需要丢弃的卡牌数量...")
        prompt_text, _ = self.context.recognize_text_in_relative_roi(
            DISCARD_PROMPT_ROI,
            "images/debug_discard_prompt.png"
        )
        if prompt_text:
            prompt_text = prompt_text.replace(" ", "") # 去除空格方便匹配
            logger.debug(f"  -> 弃牌提示 OCR 文本: '{prompt_text}'")
            # 匹配 "选择X张牌弃置" 或类似的模式
            match = re.search(r'(?:选择|弃置)(\d+)张(?:牌)?', prompt_text)
            if match:
                try:
                    count = int(match.group(1))
                    if count > 0:
                        logger.info(f"  -> 需要丢弃 {count} 张卡牌。")
                        return count
                    else:
                        logger.warning(f"  -> 解析到的弃牌数量为 0 或负数 ({count})，视为无效。")
                except ValueError:
                    logger.error(f"  -> 无法从 '{match.group(1)}' 解析弃牌数量。")
            else:
                 logger.warning(f"  -> 未能在提示 '{prompt_text}' 中匹配到弃牌数量模式。")
        else:
            logger.warning("  -> 未能 OCR 识别弃牌提示文本。")

        logger.warning("  -> 无法确定弃牌数量，将假定为 1。")
        return 1

    def _recognize_discardable_cards(self) -> List[Dict]:
        """
        使用 OCR 识别弃牌选择界面中可见的卡牌名称。
        允许识别并返回重复的卡牌名称。
        """
        if not self.context: return []
        logger.info("  -> 开始识别可丢弃卡牌 (OCR, 允许重复)...")
        discardable_cards = []
        card_index_counter = 0

        # 对弃牌卡牌名称区域进行 OCR
        _, recognized_blocks = self.context.recognize_text_in_relative_roi(
            DISCARD_CARD_NAME_ROI,
            "images/debug_discard_card_names.png" # Debug 文件名
        )

        if not recognized_blocks:
            logger.warning("  -> 弃牌卡牌名称区域 OCR 未返回任何文本块。")
            return []

        logger.debug(f"  -> 弃牌区域 OCR 原始结果: {recognized_blocks}")

        # 按索引（大致位置）排序，这有助于按界面顺序处理
        recognized_blocks.sort(key=lambda block: block[0])

        # 解析识别到的文本块
        for _, text in recognized_blocks:
            text = text.strip()
            # 简单判断是否为中文名，并且长度大于1，避免单个字符干扰
            # 你可能需要根据实际 OCR 结果调整这个过滤条件
            is_potential_card_name = bool(re.search(r'[\u4e00-\u9fff]', text)) and len(text) > 1

            if is_potential_card_name:
                # 直接添加识别到的卡牌名，不进行去重
                discardable_cards.append({"name": text, "index": card_index_counter})
                logger.debug(f"    识别到可能的可弃置卡牌名: '{text}' (索引: {card_index_counter})")
                card_index_counter += 1
            else:
                logger.debug(f"    忽略非卡牌名文本: '{text}'")


        if not discardable_cards:
             logger.warning("  -> 未能从 OCR 结果中解析出有效的可弃置卡牌名称。")

        logger.info(f"  -> 当前可见的可丢弃卡牌识别完成 (允许重复)，共 {len(discardable_cards)} 张: {[card['name'] for card in discardable_cards]}")
        return discardable_cards

    def _click_button(self, roi: Tuple[float, float, float, float], button_name: str):
        """辅助方法：点击给定 ROI 区域的中心点。"""
        if not self.context: return
        click = self.context.get_input_simulator()
        if not click:
            logger.error(f"  -> 无法获取 InputSimulator，无法点击 '{button_name}' 按钮。")
            return
        center_x = roi[0] + roi[2] / 2
        center_y = roi[1] + roi[3] / 2
        click.click_relative(center_x, center_y)
        logger.info(f"  -> 点击 '{button_name}' 按钮 (区域: {roi})。")
        time.sleep(0.5) # 点击后短暂等待

    def _choose_cards_give_up(self):
        """处理选择并弃置卡牌的完整流程 (允许重复卡牌)。"""
        if not self.context: return
        click = self.context.get_input_simulator()
        if not click:
             logger.error("  -> 无法获取 InputSimulator，无法执行弃牌。")
             return

        logger.info("--- 开始处理弃牌选择 ---")

        # 1. 确定需要丢弃几张牌
        discard_count = self._parse_discard_count()
        if discard_count <= 0:
            logger.warning("  -> 需要丢弃的卡牌数量为 0 或无法确定，跳过弃牌。")
            # 考虑是否需要点击取消，以防界面卡住
            # self._click_button(CANCEL_DISCARD_BUTTON_ROI, "取消(因数量为0)")
            return # 如果数量为0，通常不需要操作，直接返回

        # 2. 识别当前可选的手牌 (包含滚动重试逻辑)
        max_recognition_attempts = 3 # 识别尝试次数
        discardable_cards = [] # List[Dict{'name': str, 'index': int}]
        for attempt in range(max_recognition_attempts):
            discardable_cards = self._recognize_discardable_cards()
            if discardable_cards: # 如果识别到卡牌，则停止尝试
                break
            elif attempt < max_recognition_attempts - 1:
                logger.warning(f"  -> 第 {attempt + 1} 次尝试未识别到可弃置卡牌，稍后重试...")
                time.sleep(0.7) # 等待一下再试
            else:
                 logger.error(f"  -> {max_recognition_attempts} 次尝试后仍未识别到任何可丢弃的卡牌。无法继续弃牌。")
                 logger.info("  -> 点击取消按钮以尝试恢复。")
                 self._click_button(CANCEL_DISCARD_BUTTON_ROI, "取消(未识别到卡牌)")
                 return

        # 3. 询问 LLM 选择丢弃的牌
        template = self.context.get_prompt_template("discard") # 使用正确的 key
        if not template:
            logger.error(f"  -> 错误：找不到 Prompt 模板 'discard'。")
            logger.warning("  -> 无法获取弃牌决策 Prompt，点击取消。")
            self._click_button(CANCEL_DISCARD_BUTTON_ROI, "取消(无Prompt)")
            return

        card_knowledge = self.context.game_knowledge.get('cards', {})
        discard_options_with_desc = []
        for idx, card in enumerate(discardable_cards):
            card_name = card['name']
            card_data = card_knowledge.get(card_name)
            description = card_data.get('description', '无描述') if card_data else '未知卡牌'
            discard_options_with_desc.append(f"{idx}:{card_name} ({description})")

        # 在 Prompt 中包含索引，帮助 LLM 理解，但仍要求返回名称
        available_cards_str_with_desc = ", ".join([f"{idx}:{card['name']}" for idx, card in enumerate(discard_options_with_desc)])
        format_data = {
            "discard_count": discard_count,
            "available_cards": available_cards_str_with_desc,
        }
        try:
            formatted_prompt = template.format(**format_data)
        except KeyError as e:
            logger.error(f"  -> 格式化 Prompt 'discard' 时出错：缺少键 {e}")
            logger.warning("  -> 格式化弃牌决策 Prompt 出错，点击取消。")
            self._click_button(CANCEL_DISCARD_BUTTON_ROI, "取消(Prompt格式化错误)")
            return

        logger.info(f"  -> 询问 LLM 弃牌决策...")
        logger.debug(f"  -> Prompt (填充后): \"{formatted_prompt}\"")
        llm_decision = self.context.ask_llm(formatted_prompt, history_type='map')

        if not llm_decision:
            logger.warning("  -> LLM 未能提供弃牌决策。直接选择前两个。")
            llm_decision = ", ".join([card['name'] for card in discardable_cards[:discard_count]])

        # 4. 解析 LLM 的选择 (期望是逗号分隔的卡牌名，允许重复)
        chosen_card_names_raw = [name.strip() for name in llm_decision.split(',') if name.strip()]
        logger.info(f"  -> LLM 原始决策: {chosen_card_names_raw}")

        # --- 新的验证逻辑 ---
        # 检查 LLM 返回的数量是否正确
        if len(chosen_card_names_raw) != discard_count:
            logger.warning(f"  -> LLM 返回了 {len(chosen_card_names_raw)} 张卡牌，但需要丢弃 {discard_count} 张。决策无效，点击取消。")
            self._click_button(CANCEL_DISCARD_BUTTON_ROI, "取消(LLM选择数量错误)")
            return

        # 检查 LLM 返回的每张牌是否都在可选列表中 (考虑数量)
        from collections import Counter
        available_card_counts = Counter(card['name'] for card in discardable_cards)
        chosen_card_counts = Counter(chosen_card_names_raw)

        valid_selection = True
        for name, count in chosen_card_counts.items():
            # 尝试模糊匹配 LLM 的名称到可用名称
            matched_available_name = None
            if name in available_card_counts:
                matched_available_name = name
            else:
                # 简单包含匹配
                for available_name in available_card_counts.keys():
                     if name in available_name or available_name in name:
                         logger.info(f"  -> 验证时模糊匹配 LLM 决策 '{name}' 到可选卡牌 '{available_name}'")
                         matched_available_name = available_name
                         break

            if matched_available_name:
                if count > available_card_counts.get(matched_available_name, 0):
                    logger.warning(f"  -> LLM 选择了 {count} 张 '{name}' (匹配到 {matched_available_name})，但当前可见列表中只有 {available_card_counts.get(matched_available_name, 0)} 张。决策无效。")
                    valid_selection = False
                    break
            else:
                logger.warning(f"  -> LLM 选择的卡牌 '{name}' 未在当前可见的可选列表中找到。决策无效。")
                valid_selection = False
                break

        if not valid_selection:
            logger.info("  -> LLM 的选择验证失败，点击取消。")
            self._click_button(CANCEL_DISCARD_BUTTON_ROI, "取消(LLM选择无效)")
            return

        logger.info(f"  -> LLM 决定丢弃 (验证通过): {chosen_card_names_raw}")

        # 5. 定位并点击选择的卡牌 (按 LLM 返回的顺序和重复次数点击)
        selected_count = 0
        max_scroll_attempts = 5 # 最多尝试滚动次数来查找一张牌

        # 直接迭代 LLM 返回的名称列表
        for card_name_to_click in chosen_card_names_raw:
            found_and_clicked_this_instance = False
            for scroll_attempt in range(max_scroll_attempts + 1): # 0是不滚动，1到max是滚动后尝试
                logger.info(f"  -> 尝试定位并点击卡牌 '{card_name_to_click}' (滚动尝试 {scroll_attempt}/{max_scroll_attempts})...")

                card_coords_in_roi = None
                find_text_method = getattr(self.context, 'find_text_coordinates_in_relative_roi', None)
                if callable(find_text_method):
                    try:
                        # 每次都查找这个名字，OCR 会找到第一个匹配项
                        # 假设游戏 UI 在点击后会更新，或者重复点击第一个匹配项也能选中下一个
                        card_coords_in_roi = find_text_method(
                            card_name_to_click,
                            DISCARD_CARD_NAME_ROI
                        )
                    except Exception as ocr_find_e:
                         logger.error(f"  -> 调用 find_text_coordinates_in_relative_roi 时出错: {ocr_find_e}", exc_info=True)
                         card_coords_in_roi = None
                else:
                    logger.error("  -> GameContext 中缺少 find_text_coordinates_in_relative_roi 方法，无法定位卡牌。")
                    break # 严重错误，中止查找此卡牌

                if card_coords_in_roi:
                    rel_x, rel_y, rel_w, rel_h = card_coords_in_roi
                    logger.info(f"  -> OCR 定位到卡牌 '{card_name_to_click}' 在名称区域内坐标: x={rel_x:.3f}, y={rel_y:.3f}")

                    # --- 计算点击坐标 (与之前相同) ---
                    roi_left, roi_top, roi_width, roi_height = DISCARD_CARD_NAME_ROI
                    click_x = roi_left + (rel_x + rel_w / 2) * roi_width
                    click_y = roi_top + (rel_y + rel_h / 2) * roi_height
                    click_x = max(0.0, min(1.0, click_x))
                    click_y = max(0.0, min(1.0, click_y))

                    logger.info(f"  -> 计算点击坐标 (屏幕相对): ({click_x:.3f}, {click_y:.3f})")
                    click.click_relative(click_x, click_y)
                    logger.info(f"  -> 点击选择卡牌 '{card_name_to_click}'。")
                    selected_count += 1
                    found_and_clicked_this_instance = True
                    time.sleep(0.8) # 等待点击生效和可能的动画/状态更新
                    break # 成功点击，跳出滚动循环，处理 LLM 列表中的下一个名称

                # 如果卡牌未找到，并且还有滚动次数
                elif scroll_attempt < max_scroll_attempts:
                    logger.info(f"  -> 卡牌 '{card_name_to_click}' 未在当前视图找到，尝试向下滚动...")
                    # 滚动逻辑 (与之前相同)
                    scroll_area_center_x = DISCARD_CARD_NAME_ROI[0] + DISCARD_CARD_NAME_ROI[2] / 2
                    scroll_start_y = DISCARD_CARD_NAME_ROI[1] + DISCARD_CARD_NAME_ROI[3] * 0.8
                    scroll_end_y = DISCARD_CARD_NAME_ROI[1] + DISCARD_CARD_NAME_ROI[3] * 0.2
                    drag_method = getattr(click, 'drag_relative', None)
                    if callable(drag_method):
                         drag_method(scroll_area_center_x, scroll_start_y, scroll_area_center_x, scroll_end_y, duration=0.4)
                         time.sleep(1.2)
                    else:
                         logger.error("  -> InputSimulator 没有 drag_relative 方法，无法滚动！中止查找此卡牌。")
                         break
                else:
                    # 滚动次数用尽仍未找到
                    logger.error(f"  -> 滚动 {max_scroll_attempts} 次后仍未找到卡牌 '{card_name_to_click}'。")
                    # 标记未找到，将在下面处理

            # 如果尝试了所有滚动次数后，仍然没有找到并点击该卡牌
            if not found_and_clicked_this_instance:
                logger.error(f"  -> 最终无法定位或点击 LLM 选择的卡牌 '{card_name_to_click}' (这是第 {selected_count + 1} 张要选的牌)。中止弃牌流程。")
                logger.info("  -> 点击取消按钮以尝试恢复。")
                self._click_button(CANCEL_DISCARD_BUTTON_ROI, "取消(无法定位卡牌)")
                return # 中止整个弃牌过程

        # 6. 检查是否成功点击了所需数量的卡牌
        # 由于我们是按 LLM 返回的数量循环点击，如果中途没有因错误退出，selected_count 应该等于 discard_count
        if selected_count == discard_count:
            logger.info(f"  -> 已成功尝试点击 {selected_count} / {discard_count} 张卡牌进行丢弃。")
            # 7. 点击 "确定" 按钮
            logger.info("  -> 点击确定按钮完成弃牌。")
            self._click_button(CONFIRM_DISCARD_BUTTON_ROI, "确定")
            time.sleep(1.0) # 等待弃牌动画或状态更新
            logger.info("--- 完成弃牌选择 ---")
        else:
            # 这个分支理论上不应该执行到，除非上面循环逻辑有误或中途出错但未 return
            logger.error(f"  -> 弃牌点击循环结束后，实际点击数 ({selected_count}) 与所需数量 ({discard_count}) 不符。")
            logger.info("  -> 点击取消按钮以尝试恢复。")
            self._click_button(CANCEL_DISCARD_BUTTON_ROI, "取消(点击计数异常)")

    def _check_discard(self) -> bool:
        """检查是否有弃牌提示"""
        if not self.context: return False
        logger.info("  -> 检查是否有弃牌提示...")
        discard_text, _ = self.context.recognize_text_in_relative_roi(
            DISCARD_PROMPT_ROI,
            "images/debug_discard_prompt.png"
        )
        if discard_text and "选择" in discard_text:
            logger.info("  -> 检测到弃牌提示。")
            return True
        else:
            logger.info("  -> 未检测到弃牌提示。")
            return False

    def _click_end_turn(self):
        """点击结束回合按钮"""
        if not self.context: return
        click = self.context.get_input_simulator()
        if not click:
            logger.error("  -> 无法获取 InputSimulator，无法结束回合。")
            return
        center_x = END_TURN_BUTTON_ROI[0] + END_TURN_BUTTON_ROI[2] / 2
        center_y = END_TURN_BUTTON_ROI[1] + END_TURN_BUTTON_ROI[3] / 2
        click.click_relative(center_x, center_y)
        logger.info("  -> 点击结束回合按钮。")
        time.sleep(1.0) # 等待回合转换
        if self._check_discard():
            logger.info("  -> 检测到丢弃提示，等待...")
            self._choose_cards_give_up() # 选择丢弃的卡牌
            time.sleep(1.0)

    def handle(self):
        if not self.context:
            logger.error("CombatState 未设置上下文。")
            return

        logger.info(f"--- 处理 {type(self).__name__} ---")
        click = self.context.get_input_simulator()
        if not click:
             logger.error("  -> 无法获取 InputSimulator。")
             time.sleep(1)
             return

        # --- 1. 获取游戏数据 ---
        game_data = self.context.get_game_data()
        player_hp = game_data.get("c_currentHP", -1)
        player_max_hp = game_data.get("c_maxHP", -1)
        enemy_hp = game_data.get("e_currentHP", -1)
        enemy_max_hp = game_data.get("e_maxHP", -1)
        action_points = game_data.get("c_actionPoints", 0)
        logger.info(f"  -> 当前状态: 玩家HP={player_hp}/{player_max_hp}, 敌人HP={enemy_hp}/{enemy_max_hp}, 能量={action_points}")
        if player_hp < 0 and player_max_hp < 0 and enemy_hp < 0 and enemy_max_hp < 0:
            logger.error("  -> 无法获取游戏数据，可能是游戏未加载或数据错误。")
            time.sleep(3)
            game_data = self.context.get_game_data()
            player_hp = game_data.get("c_currentHP", -1)
            player_max_hp = game_data.get("c_maxHP", -1)
            enemy_hp = game_data.get("e_currentHP", -1)
            enemy_max_hp = game_data.get("e_maxHP", -1)
            action_points = game_data.get("c_actionPoints", 0)
            if player_hp < 0 and player_max_hp < 0 and enemy_hp < 0 and enemy_max_hp < 0:
                logger.error("  -> 仍然无法获取游戏数据，可能是游戏未加载或数据错误。")
                click.click_relative(0.9, 0.5) # 点击屏幕以尝试恢复
                from .map_selection import MapSelectionState
                self.context.transition_to(MapSelectionState())
                logger.info("  -> 转换到 MapSelectionState。")
                return
            return

        # --- 2. 检查战斗结束 ---
        # 失败判断
        if player_hp == 0: # 假设0为精确失败血量
            logger.info("  -> 检测到玩家 HP 为 0，战斗失败！")
            self.context.add_to_history("system", "系统提示：战斗失败。")
            # 查找并点击 "重新战斗" 按钮 (使用定义的 ROI)
            retry_center_x = RETRY_BUTTON_ROI[0] + RETRY_BUTTON_ROI[2] / 2
            retry_center_y = RETRY_BUTTON_ROI[1] + RETRY_BUTTON_ROI[3] / 2
            time.sleep(2)
            click.click_relative(retry_center_x, retry_center_y)
            logger.info(f"  -> 点击 '重新战斗' 按钮 (区域: {RETRY_BUTTON_ROI})。")
            time.sleep(5)
            logger.info("  -> 重新进入战斗...")
            self._click_button(OPEN_STORY_BUTTON_ROI, "继续冒险")
            time.sleep(5)
            from .map_selection import MapSelectionState
            self.context.transition_to(MapSelectionState())
            logger.info("  -> 转换到 MapSelectionState。")
            return
            

        # 胜利判断
        if enemy_hp == 0: # 假设0为精确胜利血量
            logger.info("  -> 检测到敌人 HP 为 0，战斗胜利！")
            time.sleep(1.5) # 等待胜利动画或结算

            self.context.add_to_history("map","system", "系统提示：战斗已胜利结束。")

            # 检查是否进入对话状态
            dialogue_text, _ = self.context.recognize_text_in_relative_roi(DIALOGUE_INDICATOR_ROI, "dialogue_check")
            has_dialogue = dialogue_text and len(dialogue_text) > 5 # 简单判断

            if has_dialogue:
                logger.info("  -> 检测到对话状态。")
                from .dialogue import DialogueRewardState
                self.context.transition_to(DialogueRewardState())
                logger.info("  -> 转换到 DialogueRewardState。")
                return

            # 点击跳过胜利动画
            time.sleep(1)
            click.click_relative(0.9, 0.5)
            logger.info("  -> 点击屏幕跳过胜利动画。")
            time.sleep(1)

            # 检查是否直接进入升级状态
            upgrade_text, _ = self.context.recognize_text_in_relative_roi(UPGRADE_INDICATOR_ROI, "upgrade_check")
            has_upgrade = upgrade_text and ("升级" in upgrade_text or "恭喜" in upgrade_text)

            if has_upgrade:
                logger.info("  -> 检测到升级状态。")
                from .upgrade import UpgradeState
                self.context.transition_to(UpgradeState())
                logger.info("  -> 转换到 UpgradeState。")
                return

            # 如果既没有对话也没有升级，认为战斗结束，返回地图
            # 可能需要点击屏幕任意位置确认一下
            logger.info("  -> 未检测到对话或升级，点击屏幕确认后返回地图。")
            click.click_relative(0.9, 0.5)
            time.sleep(1)
            from .map_selection import MapSelectionState
            self.context.transition_to(MapSelectionState())
            logger.info("  -> 转换到 MapSelectionState。")
            return

        # --- 3. 判断是否为玩家回合 ---
        is_player_turn = False
        check_point_color = self.context.get_pixel_color(*PLAYER_TURN_CHECK_POINT)

        if check_point_color:
            logger.debug(f"  -> 回合结束按钮检查点 {PLAYER_TURN_CHECK_POINT} 颜色 (BGR): {check_point_color}")
            if self._is_color_close(check_point_color, PLAYER_TURN_COLOR_BGR, COLOR_TOLERANCE):
                is_player_turn = True
                logger.info(f"  -> 检查点颜色匹配玩家回合颜色 {PLAYER_TURN_COLOR_BGR} (容差 {COLOR_TOLERANCE})，判断为玩家回合。")
            elif self._is_color_close(check_point_color, ENEMY_TURN_COLOR_BGR, COLOR_TOLERANCE):
                is_player_turn = False
                logger.info(f"  -> 检查点颜色匹配敌方回合颜色 {ENEMY_TURN_COLOR_BGR} (容差 {COLOR_TOLERANCE})，判断为敌方回合。")
            else:
                # 颜色不匹配任何预设值，可以添加备用逻辑，如 OCR
                logger.warning(f"  -> 检查点颜色 {check_point_color} 不匹配预设值 (容差 {COLOR_TOLERANCE})。尝试 OCR 备用逻辑。")
                end_turn_text, _ = self.context.recognize_text_in_relative_roi(END_TURN_BUTTON_ROI, "end_turn_button_text")
                if end_turn_text and "回合结束" in end_turn_text.replace(" ",""):
                     logger.info("  -> OCR 备用：文本包含 '回合结束'，假定为玩家回合。")
                     is_player_turn = True
                else:
                     logger.info("  -> OCR 备用：文本未识别或不包含 '回合结束'，假定为敌方回合。")
                     is_player_turn = False # 默认非玩家回合
        else:
            logger.error(f"  -> 无法获取检查点 {PLAYER_TURN_CHECK_POINT} 的颜色。无法确定回合，将等待...")
            is_player_turn = False # 无法获取颜色，等待

        if not is_player_turn:
            logger.info("  -> 当前非玩家回合，等待...")
            time.sleep(1.0) # 等待一段时间再检查
            return # 保持在 CombatState

        # --- 4. 玩家回合：获取手牌 ---
        logger.info("  -> 当前为玩家回合，开始决策...")
        click.click_relative(0.9, 0.5)
        time.sleep(0.5)
        hand_cards = self._recognize_hand()
        if not hand_cards:
            logger.warning("  -> 未识别到任何手牌。可能无法行动，尝试结束回合。")
            self._click_end_turn()
            return # 结束当前 handle

        # 格式化手牌信息给 LLM
        hand_cards_str = ", ".join([f"{card['name']}({card['cost']}费)" for card in hand_cards]) if hand_cards else "无"

        # --- 5. 玩家回合：构建 Prompt 并询问 LLM ---
        prompt_key = "combat_decision"
        template = self.context.get_prompt_template(prompt_key)
        if not template:
            logger.error(f"  -> 错误：找不到 Prompt 模板 '{prompt_key}'。")
            logger.warning("  -> 无法获取战斗决策 Prompt，执行默认操作：结束回合。")
            self._click_end_turn()
            return
        
        card_knowledge = self.context.game_knowledge.get('cards', {})
        hand_cards_with_desc = []
        if hand_cards:
            for card in hand_cards:
                card_name = card['name']
                card_cost = card['cost']
                card_data = card_knowledge.get(card_name)
                description = card_data.get('description', '无描述') if card_data else '未知卡牌'
                hand_cards_with_desc.append(f"{card_name} ({card_cost}费, {description})")
        hand_cards_str_with_desc = ", ".join(hand_cards_with_desc) if hand_cards_with_desc else "无"

        # 准备填充 prompt 的数据
        format_data = {
            "p_hp": player_hp if player_hp != -1 else "N/A",
            "p_max_hp": player_max_hp if player_max_hp != -1 else "N/A",
            "p_energy": action_points,
            "hand_cards": hand_cards_str_with_desc,
            "e_hp": enemy_hp if enemy_hp != -1 else "N/A",
            "e_max_hp": enemy_max_hp if enemy_max_hp != -1 else "N/A",
        }
        try:
            # 使用 safe=True 可以在缺少键时保留占位符，而不是抛出错误
            # formatted_prompt = template.format_map(SafeDict(format_data))
            # 或者确保所有键都存在
             formatted_prompt = template.format(**format_data)
        except KeyError as e:
            logger.error(f"  -> 格式化 Prompt '{prompt_key}' 时出错：缺少键 {e}")
            logger.warning("  -> 格式化战斗决策 Prompt 出错，执行默认操作：结束回合。")
            self._click_end_turn()
            return

        logger.info(f"  -> 询问 LLM 战斗决策...")
        logger.debug(f"  -> Prompt (填充后): \"{formatted_prompt}\"")
        llm_decision = self.context.ask_llm(formatted_prompt, history_type='map')

        # --- 6. 玩家回合：解析并执行 LLM 决策 ---
        action_taken = False
        if llm_decision:
            llm_decision = llm_decision.strip() # 清理前后空格
            logger.info(f"  -> LLM 决策：'{llm_decision}'")

            # 判断是否结束回合
            if "结束回合" in llm_decision or "end turn" in llm_decision.lower():
                logger.info("  -> LLM 决定结束回合。")
                self._click_end_turn()
                action_taken = True
            else:
                # 假设回复的是卡牌名称
                card_to_play_name = llm_decision
                logger.info(f"  -> LLM 决定使用卡牌：'{card_to_play_name}'")

                # --- 新逻辑：先检查费用，再用 OCR 定位 ---
                # 1. 查找卡牌以获取费用 (仍然需要 _find_card_in_hand)
                click.click_relative(0.9, 0.5)
                card_info = self._find_card_in_hand(card_to_play_name, hand_cards)

                if card_info:
                    # 2. 检查费用是否足够
                    if action_points >= card_info['cost']:
                        logger.info(f"  -> 找到卡牌 '{card_info['name']}' (费用 {card_info['cost']})，能量充足 ({action_points})。尝试 OCR 定位...")

                        # 3. --- 使用 OCR 定位卡牌位置 ---
                        card_coords_in_roi = None
                        # 检查方法是否存在且可调用
                        find_text_method = getattr(self.context, 'find_text_coordinates_in_relative_roi', None)
                        if callable(find_text_method):
                            try:
                                # 使用 _find_card_in_hand 找到的精确名称进行 OCR 匹配
                                click.click_relative(0.9, 0.5)
                                card_coords_in_roi = find_text_method(
                                    card_info['name'], # 使用从手牌信息中匹配到的确切名称
                                    HAND_TEXT_ROI
                                )
                            except Exception as ocr_find_e:
                                 logger.error(f"  -> 调用 find_text_coordinates_in_relative_roi 时出错: {ocr_find_e}", exc_info=True)
                                 card_coords_in_roi = None # 确保出错时为 None
                        else:
                            logger.error("  -> GameContext 中缺少 find_text_coordinates_in_relative_roi 方法或该方法不可调用，无法通过 OCR 定位卡牌。")
                            # 无法定位，执行默认操作
                            logger.info("  -> 因无法调用 OCR 定位方法，执行默认操作：结束回合。")
                            self._click_end_turn()
                            action_taken = True


                        # 4. 如果 OCR 成功定位 (并且尚未因错误而结束回合)
                        if card_coords_in_roi and not action_taken:
                            rel_x_in_roi, rel_y_in_roi, rel_w_in_roi, rel_h_in_roi = card_coords_in_roi
                            logger.info(f"  -> OCR 成功定位到卡牌 '{card_info['name']}' 在手牌区域内的相对坐标: x={rel_x_in_roi:.3f}, y={rel_y_in_roi:.3f}, w={rel_w_in_roi:.3f}, h={rel_h_in_roi:.3f}")

                            # 计算卡牌中心点在屏幕上的绝对相对坐标
                            hand_roi_left, hand_roi_top, hand_roi_width, hand_roi_height = HAND_TEXT_ROI
                            # OCR 返回的坐标是相对于 ROI 的，计算其在 ROI 内的中心点
                            center_x_in_roi = rel_x_in_roi + rel_w_in_roi / 2
                            center_y_in_roi = rel_y_in_roi + rel_h_in_roi / 2
                            # 将 ROI 内的相对中心点转换为屏幕的相对坐标
                            start_x = hand_roi_left + center_x_in_roi * hand_roi_width
                            start_y = hand_roi_top + center_y_in_roi * hand_roi_height

                            # 目标位置：屏幕水平居中，垂直方向固定
                            target_x = 0.5 # 拖拽到屏幕水平中点
                            target_y = CARD_DRAG_TARGET_Y # 预定义的垂直目标 Y 坐标

                            logger.info(f"  -> 计算拖动坐标: 从 ({start_x:.3f}, {start_y:.3f}) 到 ({target_x:.3f}, {target_y:.3f})")

                            # --- 调用拖动方法 ---
                            drag_method = getattr(click, 'drag_relative', None)
                            if callable(drag_method):
                                try:
                                    drag_method(start_x, start_y, target_x, target_y, duration=0.3) # 模拟拖拽
                                    action_taken = True
                                    time.sleep(1.5) # 等待卡牌动画和状态更新
                                    logger.info("  -> 卡牌拖动完成。")
                                except Exception as drag_e:
                                    logger.error(f"  -> 调用 drag_relative 时出错: {drag_e}", exc_info=True)
                                    logger.warning("  -> 拖动卡牌时出错，执行默认操作：结束回合。")
                                    self._click_end_turn()
                                    action_taken = True # 标记已采取行动（结束回合）
                            else:
                                logger.error("  -> InputSimulator 没有 drag_relative 方法或该方法不可调用！无法出牌。")
                                logger.warning("  -> 无法执行出牌操作，执行默认操作：结束回合。")
                                self._click_end_turn()
                                action_taken = True # 标记已采取行动（结束回合）

                            # --- 防止出现遮挡问题 ---
                            time.sleep(1.5)
                            click.click_relative(0.9, 0.5)

                        # 5. 如果 OCR 未找到卡牌 (并且尚未因错误而结束回合)
                        elif not action_taken:
                            logger.error(f"  -> OCR 未能在手牌区域 {HAND_TEXT_ROI} 中定位到卡牌 '{card_info['name']}'。")
                            logger.info("  -> 因无法通过 OCR 定位卡牌，执行默认操作：结束回合。")
                            self._click_end_turn()
                            action_taken = True

                    # 如果费用不足
                    else:
                        logger.warning(f"  -> 能量不足 ({action_points})，无法使用卡牌 '{card_info['name']}' (需要 {card_info['cost']})。")
                        logger.info("  -> 因能量不足无法出牌，执行默认操作：结束回合。")
                        self._click_end_turn()
                        action_taken = True
                # 如果 LLM 建议的卡牌在手牌中未找到 (by _find_card_in_hand)
                else:
                     logger.warning(f"  -> LLM 决定使用的卡牌 '{card_to_play_name}' 未在手牌中找到或无法识别。")
                     logger.info("  -> 因找不到指定卡牌，执行默认操作：结束回合。")
                     self._click_end_turn()
                     action_taken = True
        # 如果 LLM 没有决策
        else:
            logger.warning("  -> LLM 未能提供战斗决策。")
            logger.info("  -> 无 LLM 决策，执行默认操作：结束回合。")
            self._click_end_turn()
            action_taken = True

        # 保持在 CombatState，等待下一次 handle 调用进行状态检查
        logger.info(f"--- 结束处理 {type(self).__name__} ---")

if __name__ == "__main__":
    # --- 定义你想要查看的 ROI 区域 (相对坐标: left, top, width, height) ---
    TARGET_ROI = (0.2, 0.62, 0.6, 0.03)
    print(f"尝试捕获并显示 ROI: {TARGET_ROI}")
    print("按任意键关闭显示窗口...")
    import cv2
    import numpy as np
    from get_screen import ScreenCaptureManager
    try:
        # 初始化屏幕捕获管理器
        screen_capturer = ScreenCaptureManager()

        # 捕获整个屏幕 (假设返回 PIL Image)
        screen_capturer.capture_frame()
        pil_screenshot = screen_capturer.get_current_frame()

        if pil_screenshot is None:
            print("错误：无法捕获屏幕。")
        else:
            # --- 新增：将 PIL Image 转换为 NumPy 数组 ---
            # 确保转换为 BGR 格式，因为 OpenCV 通常使用 BGR
            full_screenshot = cv2.cvtColor(np.array(pil_screenshot), cv2.COLOR_RGB2BGR)
            # 如果你的截图工具直接捕获的是 BGR，则使用：
            # full_screenshot = np.array(pil_screenshot)
            # ------------------------------------------

            # 获取屏幕尺寸 (现在可以安全访问 .shape)
            height, width, _ = full_screenshot.shape

            # 将相对 ROI 转换为绝对像素坐标
            left = int(TARGET_ROI[0] * width)
            top = int(TARGET_ROI[1] * height)
            roi_width = int(TARGET_ROI[2] * width)
            roi_height = int(TARGET_ROI[3] * height)

            # 确保坐标和尺寸在屏幕范围内
            left = max(0, left)
            top = max(0, top)
            right = min(width, left + roi_width)
            bottom = min(height, top + roi_height)

            # 裁剪 ROI 区域
            roi_image = full_screenshot[top:bottom, left:right]

            if roi_image.size == 0:
                 print(f"错误：计算出的 ROI 区域为空。坐标: L={left}, T={top}, R={right}, B={bottom}")
            else:
                # 使用 OpenCV 显示 ROI 图像
                cv2.imshow(f"ROI Preview - {TARGET_ROI}", roi_image)

                # 等待用户按键后关闭窗口
                cv2.waitKey(0)
                cv2.destroyAllWindows()
                print("显示窗口已关闭。")

    except ImportError as e:
        print(f"错误：请确保 OpenCV (cv2), NumPy 和 Pillow 已安装。 ({e})")
        print("运行: pip install opencv-python numpy Pillow")
    except AttributeError as e:
        # 捕获可能的其他属性错误
        print(f"发生属性错误: {e}")
        print("请检查 ScreenCaptureManager.capture_screen() 的返回值类型以及后续处理。")
    except Exception as e:
        print(f"发生未预料的错误: {e}")
