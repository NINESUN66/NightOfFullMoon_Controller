from typing import TYPE_CHECKING, Set, List, Tuple, Union, Optional, Dict
import logging
import time
import re
from game_state import GameState
from .map_selection import MapSelectionState
from thefuzz import fuzz

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from game_context import GameContext # 使用相对导入

logger = logging.getLogger(__name__)


class DialogueRewardState(GameState):
    """
    处理对话或战斗胜利后的奖励选择状态。
    """
    def _remove_symbols(self, text: str) -> str:
        """移除字符串中的非字母数字字符，但保留空格。"""
        if not text:
            return ""
        # 移除所有非字母、非数字、非空格的字符
        return re.sub(r'[^\w\s]', '', text, flags=re.UNICODE)

    def handle(self):
        """
        处理对话选项或选择战斗奖励。

        1.  **识别:** 识别屏幕上的对话选项、卡牌奖励、遗物奖励等。
        2.  **决策:** 将选项信息发送给 LLM，询问选择哪个。
        3.  **定位:** 使用 OCR 找到 LLM 选择的选项文本的位置。
        4.  **执行:** 模拟点击 LLM 选择的选项或奖励。
        5.  **转换:** 完成选择后，通常转换回 `MapSelectionState`。

        Returns:
            None
        """
        if not self.context:
            logger.error("DialogueRewardState 未设置上下文。")
            return
        logger.info(f"--- 处理 {type(self).__name__} ---")

        # 定义区域
        text_region = (0.53, 0.07, 0.2, 0.13) # 对话/问题文本区域
        option_region = (0.4, 0.48, 0.2, 0.3) # 选项/奖励文本区域

        # --- 1. 识别对话/问题文本 ---
        question_text, _ = self.context.recognize_text_in_relative_roi(
            text_region,
            debug_filename="images/debug_dialogue_text.png"
        )

        # 进行基本检查，确保识别到一些内容
        if not question_text or len(question_text.strip()) < 3: # 稍微放宽长度检查
            logger.warning("  -> 未识别到有效的对话/问题文本。可能不在对话/奖励状态。")
            # 可以考虑添加一个计数器或更复杂的逻辑来决定是否退出
            time.sleep(1) # 等待重试
            return

        cleaned_question = ' '.join(question_text.split()) # 清理文本
        logger.info(f"  -> 识别到的对话/问题文本: '{cleaned_question}'")

        # --- 加载并匹配对话知识 ---
        dialogue_knowledge = self.context.game_knowledge.get("dialog", {}) # 直接访问 game_knowledge
        
        best_match_key: Optional[str] = None
        best_match_info: Optional[Dict[str, str]] = None
        best_match_score: float = 0.0
        similarity_threshold: int = 80
        matched_dialogue_info_str: str = "未找到相关对话知识。"
        processed_question_for_matching = self._remove_symbols(cleaned_question)
        logger.debug(f"  -> 用于匹配的已处理问题文本: '{processed_question_for_matching}'")

        if dialogue_knowledge and processed_question_for_matching:
            logger.info("  -> 尝试匹配对话知识库...")
            for key, info_dict in dialogue_knowledge.items():
                if not isinstance(key, str) or not isinstance(info_dict, dict):
                    logger.warning(f"  -> 对话知识库中存在格式不正确的条目: key='{key}', info='{info_dict}'")
                    continue

                # 预处理知识库中的键（移除符号）
                processed_key_for_matching = self._remove_symbols(key)
                if not processed_key_for_matching: # 如果移除符号后为空，则跳过
                    continue
                
                # logger.debug(f"  -> 比较: '{processed_question_for_matching}' vs '{processed_key_for_matching}'")
                score = fuzz.partial_ratio(processed_question_for_matching, processed_key_for_matching)
                
                if score > best_match_score:
                    best_match_score = score
                    best_match_key = key # 存储原始的 key
                    best_match_info = info_dict
            
            if best_match_key and best_match_info and best_match_score >= similarity_threshold:
                logger.info(f"  -> 匹配到对话知识: '{best_match_key}' (处理后文本相似度: {best_match_score:.2f}%)")
                try:
                    # 将字典形式的选项效果转换为字符串
                    matched_dialogue_info_str = "; ".join([f"'{opt}': {eff}" for opt, eff in best_match_info.items()])
                    logger.info(f"  -> 已知选项效果: {matched_dialogue_info_str}")
                except Exception as e:
                    logger.error(f"  -> 格式化匹配到的对话知识时出错: {e}", exc_info=True)
                    matched_dialogue_info_str = "对话知识格式化失败。"
            else:
                logger.info(f"  -> 未找到足够相似的对话知识 (最高相似度: {best_match_score:.2f}%)")
        elif not dialogue_knowledge:
            logger.warning("  -> 对话知识库为空或 'dialog' 类别不存在。")
        elif not processed_question_for_matching:
             logger.warning("  -> (处理后)无对话文本以进行匹配。")
        # --- 匹配结束 ---

        click = self.context.get_input_simulator()
        if not click:
            logger.error("  -> 无法获取 InputSimulator，无法点击选项/奖励。")
            time.sleep(1)
            return
        
        # 点击过对话,以出现选项/奖励文本
        for _ in range(3): # 使用 _ 表示循环变量未使用
            click.click_relative(0.9, 0.5) 
            time.sleep(0.1) # 短暂延时

        # --- 2. 识别选项/奖励文本 ---
        # 重新识别选项区域，因为上面的点击可能改变了屏幕内容
        options_text, indexed_options = self.context.recognize_text_in_relative_roi(
            option_region,
            debug_filename="images/debug_dialogue_options.png"
        )

        if not options_text or len(options_text.strip()) < 2: # 选项可能很短
            logger.warning("  -> 未识别到有效的对话选项/奖励文本。")
            time.sleep(1) # 等待重试
            return

        # 使用带索引的文本，如果可用且更清晰
        if indexed_options:
            cleaned_options = "\n".join([f"{idx}. {text}" for idx, text in indexed_options])
        else:
            cleaned_options = ' '.join(options_text.split()) # 清理文本
        logger.info(f"  -> 识别到的选项/奖励文本:\n{cleaned_options}")


        # --- 3. 获取 Prompt 模板 ---
        prompt_key = "dialogue_choice" # 确保 prompt.json 中有此键，并且模板包含 {dialogue_text}, {options_text}, {knowledge}
        template = self.context.get_prompt_template(prompt_key)
        if not template:
            logger.error(f"  -> 错误：找不到 Prompt 模板 '{prompt_key}'。无法进行决策。")
            time.sleep(1)
            return
        
        # --- 4. 构建 Prompt 并询问 LLM ---
        format_data = {
            "dialogue_text": cleaned_question,
            "options_text": cleaned_options, # 使用清理或格式化后的选项文本
            "knowledge": matched_dialogue_info_str
        }
        try:
            formatted_prompt = template.format(**format_data)
        except KeyError as e:
            logger.error(f"  -> 格式化 Prompt '{prompt_key}' 时出错：缺少键 {e}")
            time.sleep(1)
            return

        logger.info(f"  -> 询问 LLM 对话/奖励选择...")
        logger.debug(f"  -> Prompt (填充后): \"{formatted_prompt}\"")
        llm_decision = self.context.ask_llm(formatted_prompt, history_type='map')

        # --- 5. 解析决策，定位并执行点击 ---
        if llm_decision:
            # LLM 可能返回带序号的选项，例如 "1. xxx" 或 "xxx"，需要提取实际的选项文本
            # 简单的提取逻辑：如果以 "数字." 开头，则取后面的部分
            import re
            match = re.match(r"^\d+\s*[\.:]\s*(.*)", llm_decision.strip())
            if match:
                decision_text_to_find = match.group(1).strip()
            else:
                decision_text_to_find = llm_decision.strip()
            
            logger.info(f"  -> LLM 决策：'{llm_decision}'，将查找文本：'{decision_text_to_find}'")


            # --- 尝试用 OCR 定位 LLM 选择的文本 ---
            logger.info(f"  -> 尝试在选项区域 {option_region} 定位文本 '{decision_text_to_find}'...")
            option_coords_in_roi = self.context.find_text_coordinates_in_relative_roi(
                decision_text_to_find,
                option_region,
                debug_filename=f"images/debug_find_{decision_text_to_find.replace(' ', '_')[:20]}.png" # 限制文件名长度
            )

            if option_coords_in_roi:
                rel_x_in_roi, rel_y_in_roi, rel_w_in_roi, rel_h_in_roi = option_coords_in_roi
                logger.info(f"  -> OCR 成功定位到选项 '{decision_text_to_find}' 在选项区域内的相对坐标: x={rel_x_in_roi:.3f}, y={rel_y_in_roi:.3f}, w={rel_w_in_roi:.3f}, h={rel_h_in_roi:.3f}")

                # 计算选项中心点在屏幕上的绝对相对坐标
                option_roi_left, option_roi_top, option_roi_width, option_roi_height = option_region
                # 计算 ROI 内的相对中心点
                center_x_in_roi = rel_x_in_roi + rel_w_in_roi / 2
                center_y_in_roi = rel_y_in_roi + rel_h_in_roi / 2
                # 转换为屏幕的相对坐标
                click_x = option_roi_left + center_x_in_roi * option_roi_width
                click_y = option_roi_top + center_y_in_roi * option_roi_height

                logger.info(f"  -> 计算点击坐标 (屏幕相对): ({click_x:.3f}, {click_y:.3f})")

                # --- 执行点击 ---
                # click 实例已在前面获取
                click.click_relative(click_x, click_y)
                logger.info(f"  -> 已点击选项/奖励 '{decision_text_to_find}'。")
                time.sleep(1.5) # 等待点击生效和界面过渡

                # --- 多次点击空白区域防止出现继续对话 ---
                for _ in range(5): # 使用 _ 表示循环变量未使用
                    click.click_relative(0.9, 0.5)
                    time.sleep(0.1) # 短暂延时

                # --- 转换状态 ---
                # 完成对话/奖励选择后，通常返回地图
                time.sleep(2) # 等待界面稳定
                UPGRADE_INDICATOR_ROI = (0.4, 0.24, 0.2, 0.06) # 假设这是升级提示的区域
                # 使用新的 debug 文件名，避免与之前的冲突
                upgrade_text, _ = self.context.recognize_text_in_relative_roi(UPGRADE_INDICATOR_ROI, "images/debug_upgrade_check.png") 
                has_upgrade = upgrade_text and ("升级" in upgrade_text or "恭喜" in upgrade_text or "选择" in upgrade_text) # 扩展关键词

                if has_upgrade:
                    logger.info("  -> 检测到升级/奖励选择状态。")
                    from .upgrade import UpgradeState # 确保 UpgradeState 已定义
                    self.context.transition_to(UpgradeState())
                    logger.info("  -> 转换到 UpgradeState。")
                    return
                
                # 如果不是升级状态，再点击几次确保退出对话界面
                for _ in range(5): # 使用 _ 表示循环变量未使用
                    click.click_relative(0.9, 0.5)
                    time.sleep(0.1)

                logger.info("  -> 对话/奖励选择完成，转换到 MapSelectionState。")
                time.sleep(2) # 确保状态转换前界面稳定
                self.context.transition_to(MapSelectionState())
                return # 结束当前 handle

            else:
                logger.error(f"  -> OCR 未能在选项区域 {option_region} 中定位到 LLM 选择的文本 '{decision_text_to_find}'。")
                # 无法定位，可以选择等待或转回地图
                logger.info("  -> 因无法定位选项/奖励，将等待后重试当前状态。")
                time.sleep(1)
                # 不转换状态，允许下一次主循环再次调用 handle
                return

        else:
            logger.warning("  -> LLM 未能提供对话/奖励选择。")
            # LLM 无响应，可以选择等待或转回地图
            logger.info("  -> 因 LLM 无响应，将等待后重试当前状态。")
            time.sleep(1)
            # 不转换状态，允许下一次主循环再次调用 handle
            return