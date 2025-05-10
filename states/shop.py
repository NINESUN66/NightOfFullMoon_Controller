from typing import TYPE_CHECKING, Set, List, Tuple, Union, Optional, Dict
import logging
import time
from game_state import GameState
from .map_selection import MapSelectionState

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 使用相对导入
    
logger = logging.getLogger(__name__)


class ShopState(GameState):
    """
    处理商店交互的状态。
    """
    def handle(self):
        """
        浏览商店物品，根据 LLM 决策进行购买。

        1.  **识别:** 识别商店中的物品、价格。获取当前玩家金币数量。
        2.  **决策:** 将商店信息和当前金币发送给 LLM，询问购买哪些项目。
        3.  **执行:** 根据 LLM 决策模拟点击购买按钮或关闭商店按钮。
        4.  **转换:** 点击关闭按钮或完成购买后，转换回 `MapSelectionState`。

        Returns:
            None
        """
        if not self.context:
            logger.error("ShopState 未设置上下文。")
            return
        logger.info(f"正在处理 {type(self).__name__}...")
        # --- 识别商店物品 ---
        # 将鼠标移动到左上角防止遮挡
        click = self.context.get_input_simulator()
        click.click_relative(0.1, 0.1)
        time.sleep(0.2) # 短暂等待鼠标移动完成

        # 定义所需相对坐标区域
        # (left, top, width, height)
        regions = [
            (0.29, 0.35, 0.1, 0.05),  # 商品A名称
            (0.32, 0.655, 0.06, 0.05), # 商品A价格
            (0.46, 0.35, 0.1, 0.05),  # 商品B名称
            (0.485, 0.655, 0.06, 0.05),# 商品B价格
            (0.63, 0.35, 0.1, 0.05),  # 商品C名称
            (0.65, 0.655, 0.06, 0.05), # 商品C价格
        ]
        buy_button_coords = [
            (0.32, 0.7), # 商品A购买按钮
            (0.485, 0.7), # 商品B购买按钮
            (0.65, 0.7), # 商品C购买按钮
        ]
        leave_button_coord = (0.72, 0.27) # 离开/关闭商店按钮

        # 循环识别每个区域的文本
        shop_items_text = []
        for i, region in enumerate(regions):
            recognized_text, _ = self.context.recognize_text_in_relative_roi( # 忽略 arr 返回值
                relative_coords=region,
                debug_filename=f"images/debug_shop_region_{i}.png"
            )
            # 对价格区域的 'Oh' 进行特殊处理
            if i in [1, 3, 5] and recognized_text and "Oh" in recognized_text: # 检查是否是价格区域且包含 "Oh"
                 processed_text = recognized_text.replace("Oh", "40")
                 logger.info(f"  -> 区域 {i} 识别到 'Oh'，替换为 '40'：'{recognized_text}' -> '{processed_text}'")
                 shop_items_text.append(processed_text)
            else:
                 shop_items_text.append(recognized_text if recognized_text else "N/A")

            logger.info(f"  -> 识别到的商店区域 {i} 文本：'{shop_items_text[-1]}'")

        # 尝试构建更易读的物品列表
        items_description = ""
        card_knowledge = self.context.game_knowledge.get('cards', {})
        items_list_for_prompt = []
        try:
            if len(shop_items_text) >= 6:
                for i in range(0, 6, 2):
                    name = shop_items_text[i]
                    price = shop_items_text[i+1]
                    if name != "N/A":
                        card_data = card_knowledge.get(name)
                        description = card_data.get('description', '无描述') if card_data else '未知物品'
                        items_list_for_prompt.append(f"{name} ({description}) - 价格: {price}")
                    else:
                        items_list_for_prompt.append(f"商品{i//2 + 1}: N/A")
                items_description = "\n".join(items_list_for_prompt)
            else:
                # 处理识别不全的情况
                temp_desc = []
                for i in range(0, len(shop_items_text), 2):
                    name = shop_items_text[i]
                    price = shop_items_text[i+1] if i+1 < len(shop_items_text) else "N/A"
                    if name != "N/A":
                        card_data = card_knowledge.get(name)
                        description = card_data.get('description', '无描述') if card_data else '未知物品'
                        temp_desc.append(f"{name} ({description}) - 价格: {price}")
                    else:
                        temp_desc.append(f"商品{i//2 + 1}: N/A")
                items_description = "\n".join(temp_desc)


        except IndexError:
            logger.warning("  -> 由于缺少 OCR 结果，无法格式化所有商店物品。")
            temp_desc = []
            for i in range(0, len(shop_items_text), 2):
                name = shop_items_text[i] if i < len(shop_items_text) else "N/A"
                price = shop_items_text[i+1] if i+1 < len(shop_items_text) else "N/A"
                if name != "N/A":
                    temp_desc.append(f"{i//2 + 1}: {name} ({price}g)")
            items_description = "\n".join(temp_desc)

        logger.info(f"  -> 格式化后的商店物品：\n{items_description}")

        # 获取当前金币
        game_data = self.context.get_game_data()
        current_gold = 0 # 默认值
        if game_data and "p_money" in game_data:
            current_gold = game_data["p_money"]
            logger.info(f"  -> 当前金币（来自内存）：{current_gold}")
        else:
            logger.warning("  -> 无法从内存数据获取当前金币。尝试 OCR。")
            # TODO: 添加 OCR 金币数量的逻辑作为备用方案

        # 获取 Prompt 模板
        prompt_key = "shop_decision"
        template = self.context.get_prompt_template(prompt_key)
        if not template:
            logger.error(f"  -> 错误：找不到 Prompt 模板 '{prompt_key}'。")
            # 默认离开商店
            click.click_relative(*leave_button_coord)
            logger.warning("  -> 找不到模板，默认点击离开按钮。")
            self.context.transition_to(MapSelectionState())
            return

        # 构建 Prompt 给 LLM
        format_data = {
            "gold": current_gold,
            "items": items_description.strip() # 使用格式化后的描述
        }
        try:
            formatted_prompt = template.format(**format_data)
        except KeyError as e:
            logger.error(f"  -> 格式化 Prompt '{prompt_key}' 时出错：缺少键 {e}")
            # 默认离开商店
            click.click_relative(*leave_button_coord)
            logger.warning("  -> 格式化 Prompt 出错，默认点击离开按钮。")
            self.context.transition_to(MapSelectionState())
            return

        logger.info(f"  -> 询问 LLM 商店决策：\"{formatted_prompt}\"")
        llm_decision = self.context.ask_llm(formatted_prompt, history_type='map')

        # --- 解析 LLM 决策并执行 ---
        if llm_decision:
            logger.info(f"  -> LLM 决策：'{llm_decision}'")
            try:
                import ast
                # 使用 ast.literal_eval 安全解析列表字符串
                decision_list = ast.literal_eval(llm_decision)
                if not isinstance(decision_list, list):
                    raise ValueError("LLM 返回的不是列表格式")

                if -1 in decision_list:
                    logger.info("  -> LLM 决定不购买任何物品或执行操作。")
                    # 点击离开按钮
                    click.click_relative(*leave_button_coord)
                    logger.info("  -> 点击离开按钮。")
                    # 点击删除关卡
                    last_node_info = self.context.get_last_selected_node()
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
                else:
                    # 按顺序点击购买按钮
                    items_bought_count = 0
                    for item_index in decision_list:
                        if isinstance(item_index, int) and 1 <= item_index <= len(buy_button_coords):
                            # 将 1-based 序号转换为 0-based 索引
                            button_index = item_index - 1
                            target_coord = buy_button_coords[button_index]
                            logger.info(f"  -> LLM 决定购买物品 {item_index}。点击坐标：{target_coord}")
                            click.click_relative(*target_coord)
                            items_bought_count += 1
                            time.sleep(0.5) # 点击后稍作等待，防止操作过快
                        else:
                            logger.warning(f"  -> LLM 返回的序号 '{item_index}' 无效或超出范围 [1, {len(buy_button_coords)}]。已忽略。")
                    if items_bought_count == 0:
                         logger.info("  -> LLM 返回了购买列表，但所有序号都无效或无法处理。")
                    else:
                         logger.info(f"  -> 共购买了 {items_bought_count} 件物品。")

                    if items_bought_count >= 3:
                        logger.info("  -> LLM 购买了所有物品。")
                        # 如果全都买了关卡自动关闭消失
                        next_state = MapSelectionState()
                        self.context.transition_to(next_state)
                        logger.info("  -> 转换回 MapSelectionState。")
                    else:
                        logger.info("  -> LLM 购买了部分物品。")
                        # 点击离开按钮
                        click.click_relative(*leave_button_coord)
                        logger.info("  -> 点击离开按钮。")
                        # 点击删除关卡
                        last_node_info = self.context.get_last_selected_node()
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


            except (ValueError, SyntaxError) as e:
                logger.error(f"  -> 无法解析 LLM 的决策 '{llm_decision}' 为列表：{e}。将默认离开商店。")
            except Exception as e:
                 logger.error(f"  -> 处理 LLM 决策或点击时发生意外错误：{e}", exc_info=True)

        else:
            logger.warning("  -> LLM 未能提供商店决策。将默认离开商店。")

        # --- 离开商店 ---
        logger.info("  -> 点击离开按钮。")
        click.click_relative(*leave_button_coord)
        time.sleep(1) # 等待商店界面关闭

        # --- 转换 ---
        next_state = MapSelectionState()
        self.context.transition_to(next_state)
        logger.info("  -> 转换回 MapSelectionState。")

