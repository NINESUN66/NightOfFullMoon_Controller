from typing import TYPE_CHECKING, Set, List, Tuple, Union, Optional, Dict
import logging
import time
from game_state import GameState
from .map_selection import MapSelectionState

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 使用相对导入
    
logger = logging.getLogger(__name__)

class BlacksmithState(GameState):
    """
    处理铁匠铺（通常用于升级卡牌）事件的状态。
    """
    def __init__(self, from_upgrade_event: bool = False):
        super().__init__()
        self.from_upgrade_event = from_upgrade_event
        self.action_taken: bool = False
        self.upgradeable_cards: List[str] = []
        if self.from_upgrade_event:
            logger.info("  -> [铁匠铺] 从升级事件转换到 BlacksmithState。")
        else :
            logger.info("  -> [铁匠铺] 从其他状态转换到 BlacksmithState。")
        

    def _recognize_cards_in_scrollable_area(
        self,
        first_card_name_coords: Tuple[float, float, float, float],
        vertical_spacing: float,
        horizontal_spacing: float,
        num_columns: int,
        num_visible_rows: int,
        scroll_amount: int = -120,
        scroll_pause: float = 0.5,
        max_scrolls: int = 10
    ) -> List[str]:
        """
        通过识别单个卡牌名称区域来识别滚动网格区域内的所有卡牌名称。
        """
        if not self.context:
            logger.error("  -> [铁匠铺] 错误：上下文未设置，无法执行滚动识别。")
            return []

        all_card_names: Set[str] = set()
        scroll_count = 0
        input_sim = self.context.get_input_simulator()
        if not input_sim:
             logger.error("  -> [铁匠铺] 错误：无法获取 InputSimulator。")
             return []

        logger.info("--- [铁匠铺] 开始滚动识别可升级卡牌名称 ---")
        # 将鼠标移到左上角防止遮挡初始扫描
        input_sim.click_relative(0.85, 0.25, duration=0.1)
        time.sleep(0.2)

        while scroll_count < max_scrolls:
            current_scan_names: Set[str] = set()
            logger.info(f"  -> [铁匠铺] 滚动识别：第 {scroll_count + 1}/{max_scrolls} 次扫描...")

            # 遍历可见的行和列来计算和识别卡牌名称区域
            for i in range(num_visible_rows): # 遍历行
                current_top = first_card_name_coords[1] + i * vertical_spacing
                if current_top >= 1.0 or current_top + first_card_name_coords[3] > 1.0:
                    break
                for j in range(num_columns): # 遍历列
                    current_left = first_card_name_coords[0] + j * horizontal_spacing
                    if current_left >= 1.0 or current_left + first_card_name_coords[2] > 1.0:
                        continue # 跳到下一列

                    card_coord = (current_left, current_top, first_card_name_coords[2], first_card_name_coords[3])
                    # 对每个小区域进行 OCR
                    recognized_text, _ = self.context.recognize_text_in_relative_roi(
                        relative_coords=card_coord,
                        # debug_filename=f"images/debug_blacksmith_scroll_{scroll_count}_r{i}_c{j}.png" # 可选调试
                    )

                    if recognized_text:
                        cleaned_name = recognized_text.strip()
                        # 铁匠铺的卡牌名称通常不带 '+'，但以防万一也清理一下
                        if cleaned_name.endswith('+'):
                            cleaned_name = cleaned_name[:-1].strip()
                        if len(cleaned_name) > 1: # 避免添加空字符串或单个字符
                            current_scan_names.add(cleaned_name)

            logger.info(f"  -> [铁匠铺] 本次扫描识别到卡牌：{current_scan_names if current_scan_names else '无'}")

            # --- 检查是否有新卡牌、合并结果、滚动、增加 scroll_count 的逻辑保持不变 ---
            newly_found_cards = current_scan_names - all_card_names
            if not newly_found_cards and scroll_count > 0:
                # 最后滚动一次并扫描 (与 TavernState 逻辑一致)
                logger.info("  -> [铁匠铺] 未发现新卡牌，最后滚动一次并扫描以确认列表底部...")
                input_sim.scroll(scroll_amount)
                time.sleep(scroll_pause)
                # input_sim.click_relative(0.85, 0.25, duration=0.1) # 移开鼠标
                # time.sleep(0.2)
                final_scan_names: Set[str] = set()
                for i in range(num_visible_rows):
                    current_top = first_card_name_coords[1] + i * vertical_spacing
                    if current_top >= 1.0 or current_top + first_card_name_coords[3] > 1.0: break
                    for j in range(num_columns):
                        current_left = first_card_name_coords[0] + j * horizontal_spacing
                        if current_left >= 1.0 or current_left + first_card_name_coords[2] > 1.0: continue
                        card_coord = (current_left, current_top, first_card_name_coords[2], first_card_name_coords[3])
                        recognized_text, _ = self.context.recognize_text_in_relative_roi(relative_coords=card_coord)
                        if recognized_text:
                            cleaned_name = recognized_text.strip()
                            if cleaned_name.endswith('+'): cleaned_name = cleaned_name[:-1].strip()
                            if len(cleaned_name) > 1: final_scan_names.add(cleaned_name)
                newly_found_cards_after_last_scroll = final_scan_names - all_card_names
                if newly_found_cards_after_last_scroll:
                    logger.info(f"  -> [铁匠铺] 最后一次滚动后发现新卡牌: {newly_found_cards_after_last_scroll}")
                    all_card_names.update(newly_found_cards_after_last_scroll)
                else:
                    logger.info("  -> [铁匠铺] 最后一次滚动后未发现新卡牌，确认到达列表底部。停止滚动。")
                    break # 结束滚动

            if newly_found_cards:
                 logger.info(f"  -> [铁匠铺] 新发现的可升级卡牌：{newly_found_cards}")
                 all_card_names.update(newly_found_cards)
                 logger.info(f"  -> [铁匠铺] 当前识别到的所有可升级卡牌 ({len(all_card_names)}): {sorted(list(all_card_names))}")
            elif scroll_count == 0: # 处理第一次扫描的情况
                 all_card_names.update(current_scan_names)
                 logger.info(f"  -> [铁匠铺] 当前识别到的所有可升级卡牌 ({len(all_card_names)}): {sorted(list(all_card_names))}")

            if scroll_count < max_scrolls - 1:
                logger.info(f"  -> [铁匠铺] 向下滚动 {abs(scroll_amount)} 像素...")
                input_sim.scroll(scroll_amount)
                time.sleep(scroll_pause)
                # input_sim.click_relative(0.01, 0.01, duration=0.1) # 移开鼠标
                # time.sleep(0.2)

            scroll_count += 1
            # --- 滚动和检查逻辑结束 ---

        if scroll_count == max_scrolls:
            logger.warning(f"  -> [铁匠铺] 已达到最大滚动次数 ({max_scrolls})，可能未完全识别所有可升级卡牌。")

        logger.info(f"--- [铁匠铺] 滚动识别结束，共识别到 {len(all_card_names)} 张不重复可升级卡牌 ---")
        return sorted(list(all_card_names)) # 返回排序后的列表

    def _find_target_card_on_screen(
        self,
        target_card_name: str,
        first_card_name_coords: Tuple[float, float, float, float],
        vertical_spacing: float,
        horizontal_spacing: float,
        num_columns: int,
        num_visible_rows: int,
        scroll_attempts: int = 2, # 尝试滚动次数
        scroll_amount: int = -120,
        scroll_pause: float = 0.5
    ) -> Union[Tuple[float, float], None]:
        """
        重新扫描屏幕（可滚动）以查找特定目标卡牌的点击坐标。
        (日志已调整为铁匠铺场景)
        """
        if not self.context:
            logger.error("  -> [铁匠铺] 错误：上下文未设置，无法执行卡牌定位。")
            return None

        input_sim = self.context.get_input_simulator()
        if not input_sim:
            logger.error("  -> [铁匠铺] 错误：无法获取 InputSimulator。")
            return None

        logger.info(f"--- [铁匠铺] 开始在屏幕上定位卡牌：'{target_card_name}' ---")

        # 将鼠标移到左上角防止遮挡
        input_sim.click_relative(0.85, 0.25, duration=0.1)
        time.sleep(0.2)

        for attempt in range(scroll_attempts + 1): # +1 是为了包含初始扫描（不滚动）
            if attempt > 0:
                logger.info(f"  -> [铁匠铺] 卡牌 '{target_card_name}' 在当前视图未找到，尝试第 {attempt}/{scroll_attempts} 次向下滚动...")
                input_sim.scroll(scroll_amount)
                time.sleep(scroll_pause)
                # input_sim.click_relative(0.01, 0.01, duration=0.1) # 移开鼠标
                # time.sleep(0.2)

            logger.info(f"  -> [铁匠铺] 定位尝试 {attempt + 1}/{scroll_attempts + 1} (滚动 {attempt} 次后)...")
            # 遍历可见区域查找卡牌
            for i in range(num_visible_rows + 1): # +1 稍微多扫描一行以防卡在边界
                current_top = first_card_name_coords[1] + i * vertical_spacing
                if current_top >= 1.0: # 超出屏幕底部
                    break
                for j in range(num_columns):
                    current_left = first_card_name_coords[0] + j * horizontal_spacing
                    if current_left >= 1.0: # 超出屏幕右侧
                        continue

                    card_coord = (current_left, current_top, first_card_name_coords[2], first_card_name_coords[3])
                    # 再次检查坐标有效性
                    if not (0 <= card_coord[0] < 1 and 0 <= card_coord[1] < 1 and
                            card_coord[0] + card_coord[2] <= 1 and card_coord[1] + card_coord[3] <= 1 and
                            card_coord[2] > 0 and card_coord[3] > 0):
                        continue # 跳过无效坐标

                    recognized_text, _ = self.context.recognize_text_in_relative_roi(
                        relative_coords=card_coord,
                        # debug_filename=f"images/debug_blacksmith_find_att{attempt}_r{i}_c{j}.png" # 可选调试
                    )

                    if recognized_text:
                        cleaned_name = recognized_text.strip()
                        if cleaned_name.endswith('+'): cleaned_name = cleaned_name[:-1].strip()

                        # 完全匹配目标卡牌名称
                        if cleaned_name == target_card_name:
                            # 计算点击坐标 (与 TavernState 逻辑一致，点击卡牌图像中心区域)
                            # 卡牌的实际点击区域通常比名称区域大
                            # 假设卡牌的中心点在名称区域下方某个位置
                            click_x = card_coord[0] + card_coord[2] / 2 # 名称区域水平中心
                            # 估算卡牌图像中心 Y 坐标 (假设卡牌高度约为 vertical_spacing)
                            # 点击名称区域下方一点的位置
                            click_y = card_coord[1] + vertical_spacing / 2 # 垂直间距的一半作为偏移量
                            # 确保点击坐标在屏幕范围内
                            click_y = min(click_y, 0.98); click_y = max(click_y, 0.02)
                            click_x = min(click_x, 0.98); click_x = max(click_x, 0.02)
                            logger.info(f"  -> [铁匠铺] 找到目标卡牌 '{target_card_name}'！估计点击位置 ({click_x:.3f}, {click_y:.3f})")
                            return click_x, click_y # 返回找到的坐标

        logger.warning(f"--- [铁匠铺] 未能在屏幕上定位到卡牌：'{target_card_name}' (尝试 {scroll_attempts + 1} 次扫描) ---")
        return None

    def handle(self):
        """
        选择要升级的卡牌。根据进入方式执行不同次数的升级和离开操作。
        """
        if not self.context:
            logger.error("BlacksmithState 未设置上下文。")
            return
        logger.info(f"正在处理 {type(self).__name__} (来自升级事件: {self.from_upgrade_event})...")

        # --- 配置滚动识别参数 ---
        first_card_coords = (0.18, 0.2, 0.1, 0.05)
        v_spacing = 0.32
        h_spacing = 0.14
        cols = 5
        visible_rows = 2
        leave_button_coord = (0.86, 0.1)
        ensure_button_coord = (0.45, 0.73) # 确认按钮坐标 (如果存在)
        # ----------------------------------------------------------

        click = self.context.get_input_simulator()
        last_node_info = self.context.get_last_selected_node()

        # --- 识别卡牌 (仅在未执行操作时进行) ---
        if not self.action_taken and not self.upgradeable_cards: # 避免重复识别
            self.upgradeable_cards = self._recognize_cards_in_scrollable_area(
                first_card_name_coords=first_card_coords,
                vertical_spacing=v_spacing,
                horizontal_spacing=h_spacing,
                num_columns=cols,
                num_visible_rows=visible_rows
            )
            if not self.upgradeable_cards:
                logger.warning("  -> [铁匠铺] 未识别到任何可升级的卡牌。")
                # 如果没有卡牌，直接标记动作完成，后续会处理离开或转换
                self.action_taken = True
            else:
                 logger.info(f"  -> [铁匠铺] 识别到的所有可升级卡牌：{self.upgradeable_cards}")

        # --- 行动决策 (仅在未执行操作且有卡牌时进行) ---
        if not self.action_taken and self.upgradeable_cards:
            prompt_key = "blacksmith_upgrade"
            template = self.context.get_prompt_template(prompt_key)
            if not template:
                logger.error(f"  -> [铁匠铺] 错误：找不到 Prompt 模板 '{prompt_key}'。")
                self.action_taken = True # 标记动作完成，后续处理离开
            else:
                card_knowledge = self.context.game_knowledge.get('cards', {})
                cards_with_desc = []
                for card_name in self.upgradeable_cards: # 使用 self.upgradeable_cards
                    card_data = card_knowledge.get(card_name)
                    description = card_data.get('description', '无描述') if card_data else '未知卡牌'
                    cards_with_desc.append(f"{card_name} ({description})")

                formatted_upgradeable_cards = ", ".join(cards_with_desc)
                format_data = {"upgradeable_cards": formatted_upgradeable_cards}
                try:
                    formatted_prompt = template.format(**format_data)
                    logger.info(f"  -> [铁匠铺] 询问 LLM 卡牌升级决策：\"{formatted_prompt}\"")
                    llm_decision = self.context.ask_llm(formatted_prompt, history_type='map')

                    if llm_decision:
                        logger.info(f"  -> [铁匠铺] LLM 决策：'{llm_decision}'")
                        skip_keywords = ["不需要", "跳过", "nothing", "skip", "不升级"]
                        if any(keyword in llm_decision.lower() for keyword in skip_keywords):
                            logger.info("  -> [铁匠铺] LLM 决定不升级任何卡牌。")
                            self.action_taken = True # 标记跳过也是一种行动
                        else:
                            target_card = llm_decision.strip()
                            if target_card.endswith('+'): target_card = target_card[:-1].strip()

                            if target_card in self.upgradeable_cards:
                                card_location = self._find_target_card_on_screen(
                                    target_card_name=target_card,
                                    first_card_name_coords=first_card_coords,
                                    vertical_spacing=v_spacing,
                                    horizontal_spacing=h_spacing,
                                    num_columns=cols,
                                    num_visible_rows=visible_rows,
                                    scroll_attempts=3
                                )

                                if card_location:
                                    repetitions = 2 if self.from_upgrade_event else 1
                                    logger.info(f"  -> [铁匠铺] 定位到卡牌 '{target_card}'，准备执行 {repetitions} 次升级操作。")
                                    if click:
                                        try:
                                            click_x, click_y = card_location
                                            for i in range(repetitions):
                                                logger.info(f"  -> [铁匠铺] 执行第 {i+1}/{repetitions} 次升级点击，目标：({click_x:.3f}, {click_y:.3f})")
                                                click.click_relative(click_x, click_y)
                                                logger.info(f"  -> [铁匠铺] 第 {i+1}/{repetitions} 次点击卡牌 '{target_card}' 完成。")
                                                time.sleep(1.0) # 等待动画

                                                if ensure_button_coord:
                                                    logger.info(f"  -> [铁匠铺] 第 {i+1}/{repetitions} 次尝试点击确认按钮 {ensure_button_coord}")
                                                    click.click_relative(*ensure_button_coord)
                                                    time.sleep(1.5) # 等待确认
                                                else:
                                                    time.sleep(0.5) # 如果没确认按钮也等一下
                                                    logger.info("  -> [铁匠铺] 没有配置确认按钮坐标，跳过点击确认。")

                                                if i < repetitions - 1:
                                                    logger.info(f"  -> [铁匠铺] 第 {i+1} 次升级完成，等待 1 秒后执行下一次。")
                                                    time.sleep(1.0)
                                            self.action_taken = True # 成功执行完升级循环
                                        except Exception as e:
                                            logger.error(f"  -> [铁匠铺] 点击卡牌 '{target_card}' 或确认时发生错误: {e}", exc_info=True)
                                            self.action_taken = True # 出错也标记完成，防止卡住
                                    else:
                                        logger.error("  -> [铁匠铺] 无法获取 InputSimulator 来点击卡牌。")
                                        self.action_taken = True # 无法点击也标记完成
                                else:
                                    logger.warning(f"  -> [铁匠铺] 虽然 LLM 选择了 '{target_card}'，但在屏幕上未能定位到它。")
                                    self.action_taken = True # 找不到卡牌也标记完成
                            else:
                                logger.warning(f"  -> [铁匠铺] LLM 选择的卡牌 '{target_card}' 不在可升级列表: {self.upgradeable_cards}。")
                                self.action_taken = True # 无效选择也标记完成
                    else:
                        logger.warning("  -> [铁匠铺] LLM 未能提供升级决策。")
                        self.action_taken = True # LLM 无决策也标记完成

                except KeyError as e:
                    logger.error(f"  -> [铁匠铺] 格式化 Prompt '{prompt_key}' 时出错：缺少键 {e}")
                    self.action_taken = True # 格式化出错也标记完成
                except Exception as e:
                     logger.error(f"  -> [铁匠铺] 处理 LLM 决策时发生未知错误: {e}", exc_info=True)
                     self.action_taken = True # 未知错误也标记完成

        # --- 处理完成后的逻辑 (离开或转换) ---
        if self.action_taken:
            if self.from_upgrade_event:
                # 来自升级事件，不点击离开，直接转换回地图
                logger.info("  -> [铁匠铺] 从升级事件进入，操作完成，转换回 MapSelectionState。")
                time.sleep(1.0) # 等待状态稳定
                self.context.transition_to(MapSelectionState()) # 假设总是返回地图
                return # 结束 handle
            else:
                # 正常进入，需要点击离开按钮并删除节点
                logger.info("  -> [铁匠铺] 正常进入，操作完成或跳过，尝试点击离开按钮并删除节点。")
                if click:
                    try:
                        logger.info(f"  -> [铁匠铺] 点击离开按钮 {leave_button_coord}")
                        click.click_relative(*leave_button_coord)
                        time.sleep(1.5) # 等待界面关闭

                        # 删除节点
                        if last_node_info:
                            logger.info(f"  -> [铁匠铺] 尝试删除节点：{last_node_info}")
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
                            logger.warning("  -> [铁匠铺] 无法获取上一个节点信息，无法删除关卡。")

                        # 转换回地图
                        self.context.transition_to(MapSelectionState())
                        return # 结束 handle

                    except Exception as e:
                        logger.error(f"  -> [铁匠铺] 点击离开按钮或删除节点时出错: {e}", exc_info=True)
                        # 出错也尝试转换状态，避免卡死
                        self.context.transition_to(MapSelectionState())
                        return # 结束 handle
                else:
                    logger.error("  -> [铁匠铺] 无法获取 InputSimulator 来点击离开按钮或删除节点。")
                    # 无法点击也尝试转换状态
                    self.context.transition_to(MapSelectionState())
                    return # 结束 handle
        else:
            # 如果 action_taken 仍然是 False (例如，第一次进入 handle 且未完成识别或决策)
            # 则不执行任何操作，等待下一次 handle 调用
            logger.debug("  -> [铁匠铺] 等待识别或决策完成...")
            time.sleep(0.5) # 短暂暂停避免空转过快
            return None