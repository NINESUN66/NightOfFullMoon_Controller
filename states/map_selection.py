from typing import TYPE_CHECKING, Set, List, Tuple, Union, Optional, Dict, Any
import logging
import time
from game_state import GameState

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 使用相对导入

logger = logging.getLogger(__name__)

class MapSelectionState(GameState):
    """
    处理地图界面，使用动态识别和点击选择下一个关卡的状态。
    """

    NODE_CLICK_Y_OFFSET_REL = 12.3

    def _determine_next_state_from_node_text(self, node_text: str) -> GameState:
        """根据节点文本确定下一个状态。"""
        logger.info(f"  -> 根据节点文本 '{node_text}' 决定下一个状态...")
        if node_text == "仙女祝福":
            logger.info("  -> 仙女祝福节点，转换到 FairyBlessingState。")
            from .fairy_blessing import FairyBlessingState
            return FairyBlessingState()
        elif node_text == "铁匠铺":
            logger.info("  -> 铁匠铺节点，转换到 BlacksmithState。")
            from .black_smith import BlacksmithState
            return BlacksmithState()
        elif node_text == "老猫商店":
            logger.info("  -> 老猫商店节点，转换到 ShopState。")
            from .shop import ShopState
            return ShopState()
        elif node_text == "忘忧酒馆":
            logger.info("  -> 忘忧酒馆节点，转换到 TavernState。")
            from .tavern import TavernState
            return TavernState()
        elif node_text == "害羞的宝箱":
            logger.info("  -> 害羞的宝箱节点，转换到 ChestState。")
            from .chest import ChestState
            return ChestState()
        else:
            # 如果名称不在上面明确处理的列表中，默认为战斗或未知事件
            logger.warning(f"  -> 节点 '{node_text}' 未特别处理，默认为战斗，转换到 CombatState。")
            from .combat import CombatState
            return CombatState()

    def _calculate_absolute_click_coords(
        self,
        roi_relative_coords: Tuple[float, float, float, float],
        node_center_roi_rel: Tuple[float, float]
    ) -> Optional[Tuple[int, int]]:
        """
        计算节点中心点在屏幕上的绝对像素坐标。

        Args:
            roi_relative_coords: ROI区域相对于整个屏幕的相对坐标 (left, top, width, height)。
            node_center_roi_rel: 节点中心点相对于 ROI 区域的相对坐标 (x, y)。

        Returns:
            Optional[Tuple[int, int]]: 节点的绝对屏幕点击坐标 (x, y)，如果出错则返回 None。
        """
        if not self.context: return None

        # 1. 获取屏幕尺寸
        screen_dims = self.context.get_screen_dimensions()
        if screen_dims is None:
            logger.error("  -> 错误：无法获取屏幕尺寸来计算绝对坐标。")
            return None
        screen_width, screen_height = screen_dims

        # 2. 获取选定监视器的偏移量
        monitor_info = self.context.screen_manager.get_selected_monitor_info()
        if not monitor_info:
            logger.error("  -> 错误：无法获取监视器信息来计算绝对坐标。")
            return None
        monitor_left = monitor_info['left']
        monitor_top = monitor_info['top']
        monitor_width = monitor_info['width']
        monitor_height = monitor_info['height']


        # 3. 计算 ROI 区域在监视器内的绝对像素坐标 (相对于监视器左上角)
        roi_rel_left, roi_rel_top, roi_rel_width, roi_rel_height = roi_relative_coords
        roi_abs_left_local = int(roi_rel_left * monitor_width)
        roi_abs_top_local = int(roi_rel_top * monitor_height)
        roi_abs_width_local = int(roi_rel_width * monitor_width)
        roi_abs_height_local = int(roi_rel_height * monitor_height)

        # 4. 计算节点中心点在监视器内的绝对像素坐标 (相对于监视器左上角)
        node_center_rel_x, node_center_rel_y = node_center_roi_rel
        node_abs_x_local = roi_abs_left_local + int(node_center_rel_x * roi_abs_width_local)
        node_abs_y_local = roi_abs_top_local + int(node_center_rel_y * roi_abs_height_local)

        # 5. 计算节点中心点在全局屏幕上的绝对坐标
        global_click_x = monitor_left + node_abs_x_local
        global_click_y = monitor_top + node_abs_y_local

        logger.info(f"  -> 计算得到全局点击坐标: ({global_click_x}, {global_click_y})")
        return global_click_x, global_click_y


    def _handle_dynamic_map_selection(self):
        """
        动态识别地图节点并选择的逻辑。
        """
        if not self.context:
            logger.error("MapSelectionState 未设置上下文。")
            return

        logger.info(f"正在处理 {type(self).__name__} (动态逻辑)...")

        # 定义地图节点可能出现的区域 (需要根据实际游戏调整)
        map_nodes_coords = (0.2, 0.25, 0.6, 0.03) # (left, top, width, height) - 示例值，需要调整！
        debug_filename = "images/debug_map_nodes_recognition.png"

        # --- 1. 识别节点及其位置 ---
        recognized_nodes, roi_img = self.context.recognize_nodes_in_relative_roi(
            relative_coords=map_nodes_coords,
            debug_filename=debug_filename,
            debug_draw_boxes=True
        )

        if not recognized_nodes:
            logger.error("  -> 未能在指定区域识别到任何地图节点。")
            click = self.context.get_input_simulator()
            if click:
                click.click_relative(0.9, 0.5)
                logger.info("  -> 点击屏幕中心以尝试重新加载地图。")
                time.sleep(1.5)
            return

        # --- 2. 准备 LLM Prompt ---
        prompt_key = "map_selection"
        template = self.context.get_prompt_template(prompt_key)
        if not template:
            logger.error(f"  -> 错误：找不到 Prompt 模板 '{prompt_key}'。")
            return

        node_texts_for_prompt = []
        node_texts_indexed_string = []
        node_knowledge = self.context.game_knowledge.get('nodes', {})
        for node in recognized_nodes:
            node_text = node['text']
            node_desc = node_knowledge.get(node_text, '战斗节点')
            # 直接在文本中加入描述
            text_with_desc = f"{node_text} ({node_desc})"
            node_texts_for_prompt.append(text_with_desc)
            node_texts_indexed_string.append(f"{node['index']}: {text_with_desc}")

        simple_text_list = ', '.join(node_texts_for_prompt)
        format_data = {"text": simple_text_list}

        try:
            formatted_prompt = template.format_map(format_data) # 使用 format_map 更安全
        except KeyError as e:
            logger.error(f"  -> 格式化 Prompt '{prompt_key}' 时出错：缺少键 {e}")
            return

        logger.info(f"  -> 使用 Prompt 询问 LLM：\"{formatted_prompt}\"")
        logger.info(f"  -> 识别到的节点详情: {recognized_nodes}")

        # --- 3. 询问 LLM ---
        llm_decision = self.context.ask_llm(formatted_prompt, history_type='map')

        if llm_decision is None:
            logger.warning("  -> LLM 决策失败或返回空，无法继续。")
            return

        logger.info(f"  -> LLM 决策 (原始): '{llm_decision}'")

        # --- 4. 解析 LLM 决策并找到对应节点 ---
        chosen_node_data: Optional[Dict[str, Any]] = None
        try:
            decision_index = int(llm_decision.strip())
            for node in recognized_nodes:
                if node['index'] == decision_index:
                    chosen_node_data = node
                    break

            if chosen_node_data:
                logger.info(f"  -> 根据 LLM 决策 '{decision_index}'，选择的节点是: {chosen_node_data}")
                self.context.set_last_selected_node(chosen_node_data)
            else:
                logger.error(f"  -> 错误：LLM 决策索引 '{decision_index}' 在识别的节点中未找到。")
                return

        except (ValueError, IndexError) as e:
            logger.error(f"  -> 错误：解析 LLM 决策 '{llm_decision}' 或查找节点时出错: {e}。")
            return

        # --- 5. 计算初始点击坐标 (文本中心) ---
        initial_click_coords = self._calculate_absolute_click_coords(
            map_nodes_coords,
            chosen_node_data['center_roi_rel']
        )

        if not initial_click_coords:
            logger.error("  -> 错误：无法计算初始点击坐标。")
            return

        initial_click_x, initial_click_y = initial_click_coords

        # --- 6. 计算并应用 Y 轴偏移量 ---
        final_click_x = initial_click_x
        final_click_y = initial_click_y

        # 获取监视器高度以计算像素偏移
        monitor_info = self.context.screen_manager.get_selected_monitor_info()
        if monitor_info:
            monitor_height = monitor_info['height']
            # 计算 ROI 的像素高度
            roi_rel_height = map_nodes_coords[3] # height is the 4th element
            roi_pixel_height = int(monitor_height * roi_rel_height)

            # 计算 Y 轴像素偏移量
            pixel_offset_y = int(self.NODE_CLICK_Y_OFFSET_REL * roi_pixel_height)
            logger.info(f"  -> 应用相对 Y 偏移量 {self.NODE_CLICK_Y_OFFSET_REL} (ROI 高度 {roi_pixel_height}px), 像素偏移: {pixel_offset_y}px")

            # 应用偏移（增加 Y 值以向下移动）
            final_click_y += pixel_offset_y
        else:
            logger.warning("  -> 警告：无法获取监视器信息，无法应用 Y 轴偏移。将点击文本中心。")


        # --- 7. 执行点击 ---
        input_sim = self.context.get_input_simulator()
        logger.info(f"  -> 准备点击节点 '{chosen_node_data['text']}' 在最终全局坐标 ({final_click_x}, {final_click_y})")

        logger.info(f"  -> 第一次点击 (初始坐标): ({initial_click_x}, {initial_click_y})")
        input_sim.click(initial_click_x, initial_click_y, duration=0.1, save_debug_image=False) # 第一次点击通常不需要截图
        time.sleep(0.2)

        # ---- 点击进入关卡前的特殊处理 ----
        # 特殊处理：“下个路口” 
        if chosen_node_data['text'] == "下个路口":
            logger.info("  -> 检测到 '下个路口'，尝试删除...")
            click = self.context.get_input_simulator()
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
                time.sleep(1)

            next_state = MapSelectionState() # 删除后回到地图选择
            self.context.transition_to(next_state)
            return
        # ---- 进入关卡前的特殊处理结束 ----

        # ---- 点击进入关卡后的特殊处理 ---- 
        # 特殊处理：“商店” 
        try:
            input_sim.click(final_click_x, final_click_y, duration=0.1, save_debug_image=True)
            logger.info("  -> 点击完成。")

            # 特殊处理：“绷带” (代码不变, 使用 final_click_x, final_click_y)
            if chosen_node_data['text'] == "绷带":
                logger.info("  -> 检测到 '绷带'，执行第二次点击...")
                time.sleep(1.5)
                input_sim.click(final_click_x, final_click_y, duration=0.1, save_debug_image=True)
                logger.info("  -> 第二次点击完成。")
                next_state = MapSelectionState()
                self.context.transition_to(next_state)
                return
            # 特殊处理: "尾页"
            elif chosen_node_data['text'] == "尾页":
                time.sleep(8)
                next_state = MapSelectionState()
                self.context.transition_to(next_state)
                return

        except Exception as e:
            logger.error(f"  -> 错误：点击节点时发生异常：{e}", exc_info=True)
            return
        # ---- 点击进入关卡后的特殊处理结束 ----
        

        # --- 8. 确定并转换到下一个状态 ---
        next_state = self._determine_next_state_from_node_text(chosen_node_data['text'])
        time.sleep(1.0)
        self.context.transition_to(next_state)
        logger.info("  -> 根据节点类型转换到下一个状态。")

    def handle(self):
        """
        处理地图选择状态的主入口点。
        调用新的动态处理逻辑。
        """
        # 调用新的私有方法来处理
        self._handle_dynamic_map_selection()