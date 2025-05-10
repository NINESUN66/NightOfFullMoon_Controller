from typing import TYPE_CHECKING, Set, List, Tuple, Union, Optional, Dict
import logging
import time
from game_state import GameState

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 使用相对导入
    
logger = logging.getLogger(__name__)

class TavernState(GameState):
    """
    处理酒馆（通常用于移除卡牌）事件的状态。
    """

    def _recognize_cards_in_scrollable_area(
        self,
        first_card_name_coords: Tuple[float, float, float, float],
        vertical_spacing: float,
        horizontal_spacing: float, # 新增：卡牌名称区域左侧的水平间距
        num_columns: int,          # 新增：每行有多少张卡牌
        num_visible_rows: int,     # 修改：屏幕上一次大约可见多少行卡牌
        scroll_amount: int = -520,
        scroll_pause: float = 0.5,
        max_scrolls: int = 10
    ) -> List[str]:
        """
        通过识别单个卡牌名称区域来识别滚动网格区域内的所有卡牌名称。
        (此方法保持不变，用于初始识别)
        """
        # ... existing code ...
        if not self.context:
            logger.error("  -> 错误：上下文未设置，无法执行滚动识别。")
            return []

        all_card_names: Set[str] = set()
        scroll_count = 0
        input_sim = self.context.get_input_simulator()
        if not input_sim:
             logger.error("  -> 错误：无法获取 InputSimulator。")
             return []

        logger.info("--- 开始滚动识别网格卡牌名称 ---")
        while scroll_count < max_scrolls:
            current_scan_names: Set[str] = set()
            logger.info(f"  -> 滚动识别：第 {scroll_count + 1}/{max_scrolls} 次扫描...")

            # 遍历可见的行和列来计算和识别卡牌名称区域
            for i in range(num_visible_rows): # 遍历行
                current_top = first_card_name_coords[1] + i * vertical_spacing
                # 简单的行边界检查
                if current_top >= 1.0 or current_top + first_card_name_coords[3] > 1.0:
                    # logger.debug(f"    -> 第 {i+1} 行计算出的顶部 {current_top:.3f} 超出屏幕，停止扫描此行及后续行。")
                    break

                for j in range(num_columns): # 遍历列
                    current_left = first_card_name_coords[0] + j * horizontal_spacing
                    # 简单的列边界检查
                    if current_left >= 1.0 or current_left + first_card_name_coords[2] > 1.0:
                        # logger.debug(f"    -> 第 {j+1} 列计算出的左侧 {current_left:.3f} 超出屏幕，跳过此列。")
                        continue # 跳到下一列

                    card_coord = (
                        current_left,                # left
                        current_top,                 # top
                        first_card_name_coords[2],   # width
                        first_card_name_coords[3]    # height
                    )

                    # 对每个小区域进行 OCR
                    # logger.debug(f"    -> 正在识别区域 行{i+1},列{j+1}，坐标：{tuple(round(c, 3) for c in card_coord)}")
                    recognized_text, _ = self.context.recognize_text_in_relative_roi(
                        relative_coords=card_coord,
                        # 可选：为调试取消注释下一行
                        # debug_filename=f"images/debug_scroll_{scroll_count}_r{i}_c{j}.png"
                    )

                    if recognized_text:
                        cleaned_name = recognized_text.strip()
                        # --- 在这里添加更具体的清洗逻辑 ---
                        # 移除卡牌名称末尾可能出现的 "+"
                        if cleaned_name.endswith('+'):
                            cleaned_name = cleaned_name[:-1].strip()
                        if len(cleaned_name) > 1:
                            # logger.debug(f"      -> 识别到有效文本：'{cleaned_name}'")
                            current_scan_names.add(cleaned_name)
                        # else:
                            # logger.debug(f"      -> 识别到文本 '{cleaned_name}'，因太短或无效而被忽略。")
                    # else:
                        # logger.debug(f"      -> 区域 行{i+1},列{j+1} 未识别到文本。")

            logger.info(f"  -> 本次扫描识别到卡牌：{current_scan_names if current_scan_names else '无'}")

            # --- 检查是否有新卡牌、合并结果、滚动、增加 scroll_count 的逻辑保持不变 ---
            newly_found_cards = current_scan_names - all_card_names
            if not newly_found_cards and scroll_count > 0:
                # 在判断结束前，最后滚动一次并扫描，确保不会因为滚动时机错过最后几张卡
                logger.info("  -> 未发现新卡牌，最后滚动一次并扫描以确认列表底部...")
                input_sim.scroll(scroll_amount)
                time.sleep(scroll_pause)
                # --- 重复扫描逻辑 ---
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
                            if cleaned_name.endswith('+'):
                                cleaned_name = cleaned_name[:-1].strip()
                            if len(cleaned_name) > 1:
                                final_scan_names.add(cleaned_name)
                # --- 结束重复扫描逻辑 ---
                newly_found_cards_after_last_scroll = final_scan_names - all_card_names
                if newly_found_cards_after_last_scroll:
                    logger.info(f"  -> 最后一次滚动后发现新卡牌: {newly_found_cards_after_last_scroll}")
                    all_card_names.update(newly_found_cards_after_last_scroll)
                else:
                    logger.info("  -> 最后一次滚动后未发现新卡牌，确认到达列表底部。停止滚动。")
                    break # 确认结束，跳出 while 循环

            if newly_found_cards:
                 logger.info(f"  -> 新发现的卡牌：{newly_found_cards}")
                 all_card_names.update(newly_found_cards)
                 logger.info(f"  -> 当前识别到的所有卡牌 ({len(all_card_names)}): {sorted(list(all_card_names))}")
            elif scroll_count == 0: # 处理第一次扫描的情况
                 all_card_names.update(current_scan_names)
                 logger.info(f"  -> 当前识别到的所有卡牌 ({len(all_card_names)}): {sorted(list(all_card_names))}")

            if scroll_count < max_scrolls - 1:
                logger.info(f"  -> 向下滚动 {abs(scroll_amount)} 像素...")
                input_sim.scroll(scroll_amount)
                time.sleep(scroll_pause)

            scroll_count += 1
            # --- 滚动和检查逻辑结束 ---

        if scroll_count == max_scrolls:
            logger.warning(f"  -> 已达到最大滚动次数 ({max_scrolls})，可能未完全识别所有卡牌。")

        logger.info(f"--- 滚动识别结束，共识别到 {len(all_card_names)} 张不重复卡牌 ---")
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

        Args:
            target_card_name: 要查找的卡牌的确切名称。
            first_card_name_coords: 左上角第一个卡牌名称区域的相对坐标。
            vertical_spacing: 卡牌区域顶部的相对垂直距离。
            horizontal_spacing: 卡牌区域左侧的相对水平距离。
            num_columns: 每行卡牌数。
            num_visible_rows: 屏幕上一次可见的行数。
            scroll_attempts: 如果初次扫描未找到，尝试向下滚动的最大次数。
            scroll_amount: 每次滚动的像素量。
            scroll_pause: 滚动后暂停时间。

        Returns:
            如果找到卡牌，返回其估计的相对点击坐标 (click_x, click_y)，否则返回 None。
        """
        if not self.context:
            logger.error("  -> 错误：上下文未设置，无法执行卡牌定位。")
            return None

        input_sim = self.context.get_input_simulator()
        if not input_sim:
            logger.error("  -> 错误：无法获取 InputSimulator。")
            return None

        logger.info(f"--- 开始在屏幕上定位卡牌：'{target_card_name}' ---")

        # 将鼠标移到左上角防止遮挡
        input_sim.click_relative(0.85, 0.25, duration=0.1)
        time.sleep(0.2)

        for attempt in range(scroll_attempts + 1): # +1 是为了包含初始扫描（不滚动）
            if attempt > 0: # 如果不是第一次尝试，则滚动
                logger.info(f"  -> 卡牌 '{target_card_name}' 在当前视图未找到，尝试第 {attempt}/{scroll_attempts} 次向下滚动...")
                input_sim.scroll(scroll_amount)
                time.sleep(scroll_pause)
                # 滚动后再次将鼠标移开
                input_sim.click_relative(0.85, 0.25, duration=0.1)
                time.sleep(0.2)


            logger.info(f"  -> 定位尝试 {attempt + 1}/{scroll_attempts + 1} (滚动 {attempt} 次后)...")
            # 遍历可见的行和列
            for i in range(num_visible_rows + 1): # 多扫描一行以防卡牌部分可见
                current_top = first_card_name_coords[1] + i * vertical_spacing
                if current_top >= 1.0: break # 超出底部

                for j in range(num_columns):
                    current_left = first_card_name_coords[0] + j * horizontal_spacing
                    if current_left >= 1.0: continue # 超出右侧

                    card_coord = (
                        current_left,
                        current_top,
                        first_card_name_coords[2], # width
                        first_card_name_coords[3]  # height
                    )
                    # 检查坐标有效性
                    if not (0 <= card_coord[0] < 1 and 0 <= card_coord[1] < 1 and
                            card_coord[0] + card_coord[2] <= 1 and card_coord[1] + card_coord[3] <= 1 and
                            card_coord[2] > 0 and card_coord[3] > 0):
                        # logger.debug(f"    -> 跳过无效坐标区域: {card_coord}")
                        continue

                    # 对该区域进行 OCR
                    recognized_text, _ = self.context.recognize_text_in_relative_roi(
                        relative_coords=card_coord,
                        # debug_filename=f"images/debug_find_att{attempt}_r{i}_c{j}.png" # 取消注释以调试
                    )

                    if recognized_text:
                        cleaned_name = recognized_text.strip()
                        # 清理 "+"
                        if cleaned_name.endswith('+'):
                            cleaned_name = cleaned_name[:-1].strip()

                        # logger.debug(f"    -> 扫描区域 行{i+1},列{j+1} 识别到: '{cleaned_name}'")
                        # --- 进行比较 ---
                        if cleaned_name == target_card_name:
                            # 计算点击坐标 (水平居中于名称区域，垂直略低于名称区域)
                            click_x = card_coord[0] + card_coord[2] / 2
                            # 尝试点击卡牌图像的中心区域，假设它比名称区域大且向下延伸
                            # 这里的 vertical_spacing 可以近似认为是卡牌的高度间隔
                            click_y = card_coord[1] + vertical_spacing / 2 # 点击两行卡牌垂直间距的中间位置
                            click_y = min(click_y, 0.98) # 防止点击太靠下
                            click_y = max(click_y, 0.02) # 防止点击太靠上
                            click_x = min(click_x, 0.98)
                            click_x = max(click_x, 0.02)

                            logger.info(f"  -> 找到目标卡牌 '{target_card_name}'！估计点击位置 ({click_x:.3f}, {click_y:.3f})")
                            return click_x, click_y

        logger.warning(f"--- 未能在屏幕上定位到卡牌：'{target_card_name}' (尝试 {scroll_attempts + 1} 次扫描) ---")
        return None

    def handle(self):
        """
        选择要移除的卡牌。
        """
        if not self.context:
            logger.error("TavernState 未设置上下文。")
            return
        logger.info(f"正在处理 {type(self).__name__}...")

        # --- 配置滚动识别参数 (你需要根据实际界面调整这些值) ---
        first_card_coords = (0.18, 0.2, 0.1, 0.05) # (left, top, width, height) 第一个卡牌名称区域
        v_spacing = 0.32                           # 卡牌区域顶部的垂直间距 (重要！)
        h_spacing = 0.14                           # 卡牌区域左侧的水平间距
        cols = 5                                   # 每行有多少张卡牌
        visible_rows = 2                           # 屏幕上一次大约能看到多少行卡牌
        leave_button_coord = (0.86, 0.1)            # 离开按钮坐标
        ensure_button_coord = (0.45, 0.73)         # 确定按钮坐标
        # ----------------------------------------------------------

        # 调用滚动识别方法获取所有可移除卡牌
        removable_cards = self._recognize_cards_in_scrollable_area(
            first_card_name_coords=first_card_coords,
            vertical_spacing=v_spacing,
            horizontal_spacing=h_spacing,
            num_columns=cols,
            num_visible_rows=visible_rows
        )
        # 延迟导入以避免循环导入问题
        from .map_selection import MapSelectionState
        click = self.context.get_input_simulator()
        if not removable_cards:
            logger.warning("  -> 未识别到任何可移除的卡牌。检查坐标或界面是否正确。")
            if click:
               click.click_relative(*leave_button_coord)
               logger.info(f"  -> 点击离开按钮 {leave_button_coord}")
            else:
               logger.error("  -> 无法获取 InputSimulator 来点击离开按钮。")
            next_state = MapSelectionState()
            self.context.transition_to(next_state)
            logger.info("  -> 未识别到卡牌，转换回 MapSelectionState。")
            return

        logger.info(f"  -> 识别到的所有可移除卡牌：{removable_cards}")

        # --- 后续逻辑 (获取 Prompt, 询问 LLM) ---
        prompt_key = "tavern_removal"
        template = self.context.get_prompt_template(prompt_key)
        if not template:
            logger.error(f"  -> 错误：找不到 Prompt 模板 '{prompt_key}'。")
            # 点击离开按钮
            click = self.context.get_input_simulator()
            if click: click.click_relative(*leave_button_coord)
            self.context.transition_to(MapSelectionState())
            return

        card_knowledge = self.context.game_knowledge.get('cards', {})
        cards_with_desc = []
        for card_name in removable_cards:
            card_data = card_knowledge.get(card_name)
            description = card_data.get('description', '无描述') if card_data else '未知卡牌'
            cards_with_desc.append(f"{card_name} ({description})")

        formatted_removable_cards = ", ".join(cards_with_desc)

        format_data = {
            "removable_cards": formatted_removable_cards
        }
        try:
            formatted_prompt = template.format(**format_data)
        except KeyError as e:
            logger.error(f"  -> 格式化 Prompt '{prompt_key}' 时出错：缺少键 {e}")
            click = self.context.get_input_simulator()
            if click: 
                click.click_relative(*leave_button_coord)
                self.context.transition_to(MapSelectionState())
            return

        logger.info(f"  -> 询问 LLM 卡牌移除决策：\"{formatted_prompt}\"")
        llm_decision = self.context.ask_llm(formatted_prompt, history_type='map')

        if llm_decision:
            logger.info(f"  -> LLM 决策：'{llm_decision}'")

            # 处理不需要移除的情况
            if "不需要移除" in llm_decision:
                logger.info("  -> LLM 决定不移除任何卡牌。")
                # 点击离开按钮
                if click:
                    click.click_relative(*leave_button_coord)
                    logger.info(f"  -> 点击离开按钮 {leave_button_coord}")
                    last_node_info = self.context.get_last_selected_node() # 从 Context 获取节点信息
                    if last_node_info:
                        try:
                            # 使用正确的键 'index' 获取关卡编号
                            level_index = last_node_info['index']
                            click.delete_level(level_index) # 调用 delete_level
                            logger.info(f"  -> 已调用删除节点方法 (节点索引: {level_index})。")
                            time.sleep(1.0) # 等待地图更新
                        except KeyError:
                            logger.error(f"  -> 错误：'last_node_info' 字典中缺少 'index' 键。信息: {last_node_info}")
                        except Exception as e_del:
                            logger.error(f"  -> 调用 delete_level 时出错: {e_del}", exc_info=True)
                    else:
                        logger.warning("  -> 无法获取上一个节点信息，无法删除关卡。")

                    from .map_selection import MapSelectionState
                    next_state = MapSelectionState()
                    self.context.transition_to(next_state)
                    logger.info("  -> 转换回 MapSelectionState。")
                else:
                    logger.error("  -> 无法获取 InputSimulator 来点击离开按钮。")
                return

            # 尝试解析 LLM 返回的卡牌名称
            target_card = llm_decision.strip()
            # 清理可能的 "+"
            if target_card.endswith('+'):
                target_card = target_card[:-1].strip()

            # 检查 LLM 的决策是否在识别出的卡牌列表中
            if target_card in removable_cards:
                # --- 定位并点击卡牌 ---
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
                    try:
                        click_x, click_y = card_location
                        logger.info(f"  -> 点击位于 ({click_x:.3f}, {click_y:.3f}) 的卡牌 '{target_card}'")
                        click = self.context.get_input_simulator()
                        if click:
                            # 开始销毁该卡牌
                            click.click_relative(click_x, click_y)  # 点击卡牌
                            time.sleep(0.5)
                            click.click_relative(*ensure_button_coord)  # 点击确认按钮
                            logger.info(f"  -> 已销毁卡牌 '{target_card}'。")
                        else:
                            logger.error("  -> 无法获取 InputSimulator 来点击卡牌。")

                    except Exception as e:
                        logger.error(f"  -> 点击卡牌 '{target_card}' 时发生错误: {e}", exc_info=True)
                else:
                    logger.warning(f"  -> 虽然 LLM 选择了 '{target_card}'，但在屏幕上重新扫描时未能定位到它。")

            elif target_card.lower() == "nothing" or target_card.lower() == "skip":
                 logger.info(f"  -> LLM 决定不移除卡牌 ('{target_card}')。")
            else:
                 logger.warning(f"  -> LLM 选择的卡牌 '{target_card}' 不在识别出的可移除卡牌列表中: {removable_cards}。")

        else:
            logger.warning("  -> LLM 未能提供移除决策。")

        # --- 点击离开按钮 ---
        click = self.context.get_input_simulator()
        if click:
            time.sleep(1)
            click.click_relative(*leave_button_coord)
            logger.info(f"  -> 点击了离开按钮 {leave_button_coord}")
            time.sleep(0.5)
            node_info = self.context.get_last_selected_node()
            if node_info:
                try:
                    # 使用正确的键 'index' 获取关卡编号
                    level_index = node_info['index']
                    click.delete_level(level_index) # 调用 delete_level
                    logger.info(f"  -> 已调用删除节点方法 (节点索引: {level_index})。")
                    time.sleep(1.0) # 等待地图更新
                except KeyError:
                        logger.error(f"  -> 错误：'node_info' 字典中缺少 'index' 键。信息: {node_info}")
                except Exception as e_del:
                        logger.error(f"  -> 调用 delete_level 时出错: {e_del}", exc_info=True)
            else:
                logger.warning("  -> 无法获取上一个节点信息，无法删除关卡。")
        else:
            logger.error("  -> 无法获取 InputSimulator 来点击离开按钮。")

        next_state = MapSelectionState()
        self.context.transition_to(next_state)
        logger.info("  -> 操作完成或跳过，转换回 MapSelectionState。")

