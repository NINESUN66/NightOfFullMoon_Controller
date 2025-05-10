from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, List
from PIL import Image
import cv2
import re
import numpy as np
import json
import logging
logger = logging.getLogger(__name__)

# 导入依赖项 (假设这些类已定义在别的文件中)
from get_screen import ScreenCaptureManager
from basic_data_reader import BasicDataReader
from llm_client import LLMClient
from game_state import GameState

# 为了类型提示，避免循环导入
if TYPE_CHECKING:
    from paddleocr import PaddleOCR # 仅在类型检查时导入
    from game_state import GameState # 仅在类型检查时导入
    from llm_client import LLMClient # 仅在类型检查时导入
    from input_simulator import InputSimulator # 仅在类型检查时导入

class GameContext:
    """
    维护游戏的当前状态，并持有所有共享资源。
    负责状态转换和将请求委托给当前状态处理。
    """

    def __init__(
        self,
        screen_manager: ScreenCaptureManager,
        data_reader: BasicDataReader,
        ocr_engine: Optional['PaddleOCR'], # ocr_engine 可能为 None
        llm_client: 'LLMClient', # LLM 客户端实例
        input_simulator: 'InputSimulator',
        initial_state: 'GameState', # 必须提供一个初始状态
        prompt_file: str = "prompt.json",
        knowledge_file='game_knowledge.json'
    ):
        """
        初始化游戏上下文。

        Args:
            screen_manager: ScreenCaptureManager 的实例。
            data_reader: BasicDataReader 的实例。
            ocr_engine: PaddleOCR 的实例或 None。
            llm_client: LLMClient 的实例。
            initial_state: 游戏的初始状态对象。
        """
        self.screen_manager: ScreenCaptureManager = screen_manager
        self.data_reader: BasicDataReader = data_reader
        self.ocr_engine: Optional['PaddleOCR'] = ocr_engine
        self.llm_client: 'LLMClient' = llm_client
        self.input_simulator: 'InputSimulator' = input_simulator
        self._current_state: 'GameState' = initial_state
        self._current_state.context = self # 让初始状态也能访问 context
        self.shared_data: Dict[str, Any] = {} # 用于存储跨状态共享的数据
        self.prompts: Dict[str, Dict[str, str]] = {}
        self.map_history: List[Dict[str, str]] = []      # 地图/菜单/商店等非战斗历史
        self.combat_history: List[Dict[str, str]] = []   # 当前战斗历史
        self._last_selected_node: Optional[Any] = None # 上一个选择的节点信息
        self.screen_width: Optional[int] = None
        self.screen_height: Optional[int] = None
        self.input_simulator.set_context(self)
        self._fetch_and_store_screen_dimensions()
        self.game_knowledge = self._load_knowledge(knowledge_file)
        self._load_prompts(prompt_file)

        logger.info(f"GameContext 初始化完成。初始状态: {type(initial_state).__name__}")

    @property
    def current_state(self) -> 'GameState':
        """获取当前状态对象。"""
        return self._current_state

    # --- 资源加载 ---
    def _load_knowledge(self, filename: str) -> Dict[str, Any]:
        """从 JSON 文件加载游戏知识库。"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                knowledge = json.load(f)
                logger.info(f"成功从 '{filename}' 加载游戏知识库。")
                return knowledge
        except FileNotFoundError:
            logger.error(f"错误：游戏知识库文件 '{filename}' 未找到。")
            return {}
        except json.JSONDecodeError:
            logger.error(f"错误：解析游戏知识库文件 '{filename}' 失败。请检查 JSON 格式。")
            return {}
        except Exception as e:
            logger.error(f"加载游戏知识库时发生未知错误: {e}", exc_info=True)
            return {}

    def _load_prompts(self, prompt_file: str):
        """从 JSON 文件加载 Prompt 模板。"""
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                self.prompts = json.load(f)
            logger.info(f"已成功从 '{prompt_file}' 加载 Prompt。")
        except FileNotFoundError:
            logger.error(f"错误：未找到 Prompt 文件 '{prompt_file}'。Prompt 将不可用。")
            self.prompts = {} #确保 prompts 是一个空字典
        except json.JSONDecodeError as e:
            logger.error(f"从 '{prompt_file}' 解码 JSON 时出错: {e}。Prompt 将不可用。")
            self.prompts = {}
        except Exception as e:
            logger.error(f"加载 Prompt 时发生意外错误: {e}", exc_info=True)
            self.prompts = {}

    # --- 内部方法 ---
    def get_knowledge(self, category: str, key: str, default: Optional[Dict] = None) -> Optional[Dict]:
        """从加载的知识库中获取特定条目的信息。"""
        if not self.game_knowledge:
            return default
        return self.game_knowledge.get(category, {}).get(key, default)

    def transition_to(self, new_state: 'GameState', **kwargs):
        """
        改变当前状态。

        Args:
            new_state: 要转换到的新的状态对象实例。
            **kwargs: 传递给新状态构造函数的额外参数。

        Returns:
            None
        """
        # 检查是否尝试转换到同一个类的实例 (更精确的检查)
        if type(self._current_state) == type(new_state):
             logger.warning(f"尝试转换到相同类型的状态: {type(new_state).__name__}。可能需要重置状态或检查逻辑。")
             # 如果需要，可以在这里添加重置逻辑
             # if hasattr(self._current_state, 'reset'): self._current_state.reset()
             # return # 根据需要决定是否阻止同类型转换

        old_state_name = type(self._current_state).__name__
        new_state_name = type(new_state).__name__
        logger.info(f"状态转换: 从 {old_state_name} 到 {new_state_name} (参数: {kwargs})")

        # 传递上下文和额外参数给新状态
        new_state.context = self

        self._current_state = new_state # 更新当前状态

        # 如果进入战斗则清除战斗历史
        # from states.combat import CombatState
        # if isinstance(new_state, CombatState):
        #     logger.info("  -> 进入 CombatState，清空战斗历史。")
        #     self.clear_history('combat')

    def request(self):
        """
        将处理请求委托给当前状态对象。
        这是主循环中调用的核心方法。

        Returns:
            None
        """
        if self._current_state:
            try:
                self._current_state.handle() # 调用当前状态的处理逻辑
            except Exception as e:
                logger.error(f"处理状态 {type(self._current_state).__name__} 时出错: {e}", exc_info=True)
                # 在这里可以添加错误处理逻辑，例如转换到一个错误状态
                # self.transition_to(ErrorState())
        else:
            logger.error("错误：GameContext 中未设置当前状态。")

    # --- 资源获取方法 ---
    def _get_history_list(self, history_type: str) -> Optional[List[Dict[str, str]]]:
        """内部辅助方法，根据类型获取对应的历史列表。"""
        if history_type == 'map':
            return self.map_history
        elif history_type == 'combat':
            return self.combat_history
        else:
            logger.warning(f"警告：未知的历史记录类型 '{history_type}'。")
            return None

    def add_to_history(self, history_type: str, role: str, content: str):
        """向指定的聊天历史添加一条记录。"""
        history_list = self._get_history_list(history_type)
        if history_list is not None: # 检查是否成功获取列表
            #  # 简单的历史长度限制 (可选)
            #  MAX_HISTORY_LEN = 500 # 保留最近问答对数
            #  if len(history_list) >= MAX_HISTORY_LEN * 2:
            #      logger.debug(f"  -> 历史记录 '{history_type}' 达到上限，移除最旧条目。")
            #      # 删除最旧的两个条目 (一对问答)
            #      del history_list[0:2]

            history_list.append({"role": role, "content": content})
             # logger.debug(f"  -> 已添加到 '{history_type}' 历史记录: {role} (长度: {len(history_list)})") # Debug 输出

    def get_history(self, history_type: str) -> List[Dict[str, str]]:
        """获取指定的聊天历史记录列表。"""
        history_list = self._get_history_list(history_type)
        return history_list if history_list is not None else [] # 返回空列表如果类型无效

    def clear_history(self, history_type: str):
        """清空指定的聊天历史记录。"""
        history_list = self._get_history_list(history_type)
        if history_list is not None:
            history_list.clear()
            logger.info(f"  -> 已清空 '{history_type}' 历史记录。")


    def get_prompt_template(self, key: str) -> Optional[str]:
        """
        根据键名获取 Prompt 模板字符串。

        Args:
            key: 在 prompt.json 中定义的 Prompt 的键名 (例如 "map_selection")。

        Returns:
            Optional[str]: 对应的 Prompt 模板字符串，如果键不存在或加载失败则返回 None。
        """
        prompt_data = self.prompts.get(key)
        if prompt_data and isinstance(prompt_data, dict):
            return prompt_data.get("prompt")
        logger.warning(f"警告：键 '{key}' 的 Prompt 模板未找到或无效。")
        return None

    def get_pixel_color(self, relative_x: float, relative_y: float) -> Optional[Tuple[int, int, int]]:
        """
        获取屏幕上指定相对坐标点的 BGR 颜色值。

        Args:
            relative_x: 相对 X 坐标 (0.0 到 1.0)。
            relative_y: 相对 Y 坐标 (0.0 到 1.0)。

        Returns:
            一个包含 (B, G, R) 值的元组，如果无法获取则返回 None。
        """
        screenshot = self.get_screenshot() # 使用缓存截图提高效率
        if screenshot is None:
            logger.error("无法获取屏幕截图，无法读取像素颜色。")
            return None

        screenshot = np.array(screenshot)
        height, width, _ = screenshot.shape

        # 将相对坐标转换为绝对像素坐标
        abs_x = int(relative_x * width)
        abs_y = int(relative_y * height)

        # 边界检查
        if 0 <= abs_x < width and 0 <= abs_y < height:
            # 获取 BGR 颜色值 (注意 OpenCV 图像索引是 [y, x])
            bgr_color = screenshot[abs_y, abs_x]
            # 将 numpy.uint8 转换为标准的 int 元组
            return tuple(map(int, bgr_color))
        else:
            logger.warning(f"计算出的绝对坐标 ({abs_x}, {abs_y}) 超出屏幕范围 ({width}x{height})。")
            return None

    def get_screenshot(self) -> Optional[Image.Image]:
        """
        获取当前屏幕截图。

        Returns:
            Pillow Image 对象，如果截图失败则返回 None。
        """
        return self.screen_manager.capture_frame()

    def get_input_simulator(self) -> 'InputSimulator':
        """获取输入模拟器实例。"""
        return self.input_simulator

    def get_game_data(self) -> Optional[Dict[str, Any]]:
        """
        通过内存读取器获取游戏数据。

        Returns:
            包含游戏数据的字典，如果读取失败则返回 None。
        """
        return self.data_reader.read_data()

    def get_ocr_engine(self) -> Optional['PaddleOCR']:
        """
        获取 OCR 引擎实例。

        Returns:
            PaddleOCR 实例或 None (如果初始化失败)。
        """
        return self.ocr_engine

    def find_text_coordinates_in_relative_roi(
        self,
        text_to_find: str,
        relative_coords: Tuple[float, float, float, float],
        debug_filename: Optional[str] = None
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        在指定的相对屏幕区域 (ROI) 内查找特定文本，并返回其在该 ROI 内的相对坐标。

        Args:
            text_to_find: 要查找的文本字符串。
            relative_coords: 包含 (left, top, width, height) 相对比例的元组，定义了查找区域。
            debug_filename: (可选) 保存裁剪区域图像的调试文件名。

        Returns:
            Optional[Tuple[float, float, float, float]]:
            如果找到文本，返回其在 *输入 relative_coords 定义的区域内* 的相对坐标 (x, y, width, height)。
            x, y 是左上角的相对坐标 (0.0-1.0)。
            width, height 是相对宽度和高度 (0.0-1.0)。
            如果未找到文本或发生错误，则返回 None。
        """
        logger.info(f"  -> 开始在 ROI {relative_coords} 中查找文本 '{text_to_find}'...")

        # 1. 获取截图
        now_frame = self.get_screenshot()
        if now_frame is None:
            logger.error("  -> 错误：获取屏幕截图失败，无法查找文本坐标。")
            return None

        # 2. 计算绝对坐标
        absolute_roi = self._calculate_absolute_roi(now_frame, relative_coords)
        if absolute_roi is None:
            # 错误已在 _calculate_absolute_roi 中记录
            return None

        # 3. 裁剪图像
        roi_image_pil = self._crop_image_roi(now_frame, absolute_roi, debug_filename)
        if roi_image_pil is None:
            # 错误已在 _crop_image_roi 中记录
            return None

        # 检查裁剪后的图像是否有效
        if roi_image_pil.width == 0 or roi_image_pil.height == 0:
             logger.error(f"  -> 错误：裁剪后的 ROI 图像尺寸无效 ({roi_image_pil.width}x{roi_image_pil.height})。")
             return None

        # 4. 获取 OCR 引擎
        ocr_engine = self.get_ocr_engine()
        if ocr_engine is None:
            logger.error("  -> 错误：OCR 引擎不可用，无法查找文本坐标。")
            return None

        try:
            # 5. 对 ROI 图像执行 OCR
            # 转换为 OpenCV 格式 (BGR)
            roi_image_cv = cv2.cvtColor(np.array(roi_image_pil), cv2.COLOR_RGB2BGR)
            # 执行 OCR，获取详细结果（包括包围盒）
            ocr_result = ocr_engine.ocr(roi_image_cv, cls=True) # 确保 cls=True 以获取方向分类（如果需要）
            logger.debug(f"  -> ROI 内 OCR 原始结果: {ocr_result}")

            # 6. 遍历 OCR 结果查找匹配文本
            if ocr_result and ocr_result[0] is not None:
                for detection_info in ocr_result[0]: # PaddleOCR v3+ 返回 List[List[...]]
                    # detection_info 结构通常是 [bbox, (text, score)]
                    if len(detection_info) == 2:
                        bbox = detection_info[0] # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                        text_info = detection_info[1]
                        if len(text_info) == 2:
                            recognized_text = text_info[0].strip()
                            # score = text_info[1] # 可以获取置信度

                            # --- 检查文本是否匹配 ---
                            # 可以根据需要调整匹配逻辑（例如，不区分大小写，包含关系等）
                            if text_to_find.strip() == recognized_text:
                                logger.info(f"  -> 找到匹配文本 '{recognized_text}'!")

                                # 7. 提取边界框并计算相对坐标
                                roi_width, roi_height = roi_image_pil.size

                                # bbox 中的坐标是相对于 roi_image_cv 的绝对像素坐标
                                # 计算包围盒的最小外接矩形 (min_x, min_y, max_x, max_y)
                                try:
                                    all_x = [int(p[0]) for p in bbox]
                                    all_y = [int(p[1]) for p in bbox]
                                    min_x, min_y = min(all_x), min(all_y)
                                    max_x, max_y = max(all_x), max(all_y)

                                    # 确保坐标在 ROI 图像内 (理论上应该在，但做个检查)
                                    min_x = max(0, min_x)
                                    min_y = max(0, min_y)
                                    max_x = min(roi_width, max_x)
                                    max_y = min(roi_height, max_y)

                                    # 计算相对于 ROI 区域的相对坐标 (0.0 - 1.0)
                                    rel_x = min_x / roi_width
                                    rel_y = min_y / roi_height
                                    rel_w = (max_x - min_x) / roi_width
                                    rel_h = (max_y - min_y) / roi_height

                                    logger.info(f"  -> 文本 '{recognized_text}' 在 ROI 内的相对坐标: x={rel_x:.4f}, y={rel_y:.4f}, w={rel_w:.4f}, h={rel_h:.4f}")
                                    return (rel_x, rel_y, rel_w, rel_h)
                                except Exception as calc_e:
                                     logger.error(f"  -> 计算边界框相对坐标时出错: {calc_e}", exc_info=True)
                                     return None # 计算出错，返回 None

            # 如果循环结束仍未找到
            logger.warning(f"  -> 未能在 ROI 内找到完全匹配的文本 '{text_to_find}'。")
            return None

        except Exception as e:
            logger.error(f"  -> 在 ROI 内执行 OCR 或处理结果时出错: {e}", exc_info=True)
            return None


    def _ocr_image_region_with_boxes(self, roi_image: Image.Image) -> List[Dict[str, Any]]:
        """
        对指定的图像区域执行 OCR，并返回包含边界框的详细结果。

        Args:
            roi_image: 要识别的 PIL 图像区域。

        Returns:
            List[Dict[str, Any]]: 一个字典列表，每个字典包含:
                - 'text': (str) 识别到的文本。
                - 'bbox': (List[List[int]]) 文本在 roi_image 内的像素坐标边界框 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]。
                - 'score': (float) 置信度。
            如果 OCR 引擎不可用或出错，则返回空列表。
        """
        ocr_engine = self.get_ocr_engine()
        if ocr_engine is None:
            logger.error("  -> 错误：OCR 引擎不可用于识别。")
            return []
        if roi_image.width == 0 or roi_image.height == 0:
             logger.error(f"  -> 错误：用于 OCR 的 ROI 图像尺寸无效 ({roi_image.width}x{roi_image.height})。")
             return []

        detailed_results = []
        try:
            # 转换为 OCR 格式 (BGR)
            roi_image_cv = cv2.cvtColor(np.array(roi_image), cv2.COLOR_RGB2BGR)

            # OCR 识别
            ocr_result = ocr_engine.ocr(roi_image_cv, cls=True)
            logger.debug(f"  -> OCR 详细原始结果: {ocr_result}") # Debug 输出

            if ocr_result and ocr_result[0] is not None:
                for line in ocr_result: # PaddleOCR v3+ returns List[List[...]]
                    if line:
                        for detection_info in line:
                             # detection_info 结构通常是 [bbox, (text, score)]
                            if len(detection_info) == 2:
                                bbox = detection_info[0] # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                                text_info = detection_info[1]
                                if len(text_info) == 2:
                                    recognized_text = text_info[0].strip()
                                    score = text_info[1]
                                    if recognized_text: # 仅添加非空文本结果
                                        detailed_results.append({
                                            'text': recognized_text,
                                            'bbox': bbox,
                                            'score': score
                                        })
            logger.info(f"  -> 从 ROI 提取了 {len(detailed_results)} 个详细 OCR 结果。")
            return detailed_results
        except Exception as e:
            logger.error(f"  -> OCR 过程中出错: {e}", exc_info=True)
            return []

    def recognize_nodes_in_relative_roi(
        self,
        relative_coords: Tuple[float, float, float, float],
        debug_filename: Optional[str] = None,
        debug_draw_boxes: bool = False # 新增：是否在调试图像上绘制边界框
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Image.Image]]:
        """
        识别相对坐标定义的屏幕区域内的节点（文本及其位置）。

        Args:
            relative_coords: 包含 (left, top, width, height) 相对比例的元组，定义查找区域。
            debug_filename: (可选) 保存裁剪区域图像的调试文件名。
            debug_draw_boxes: (可选) 如果为 True 且提供了 debug_filename，将在保存的图像上绘制识别到的边界框。

        Returns:
            Tuple[Optional[List[Dict[str, Any]]], Optional[Image.Image]]:
            一个元组，包含：
            - 第一个元素：节点信息列表。每个节点是一个字典，包含：
                - 'index': (int) 节点序号 (从 1 开始)。
                - 'text': (str) 识别到的节点文本。
                - 'bbox_roi_abs': (List[List[int]]) 文本在 ROI 图像内的绝对像素边界框。
                - 'bbox_roi_rel': (Tuple[float, float, float, float]) 文本在 ROI 图像内的相对边界框 (x, y, w, h)。
                - 'center_roi_rel': (Tuple[float, float]) 文本中心点在 ROI 图像内的相对坐标 (x, y)。
                - 'score': (float) OCR 置信度。
              如果识别失败或未找到节点，则为 None。
            - 第二个元素：裁剪出的 ROI 区域的 PIL Image 对象 (用于调试或进一步处理)，如果失败则为 None。
        """
        # 1. 获取 ROI 图像
        roi_image = self.get_image_in_relative_roi(relative_coords, debug_filename=None) # 暂时不保存，后面可能绘制
        if roi_image is None:
            logger.error("  -> 无法获取 ROI 图像。")
            return None, None
        if roi_image.width == 0 or roi_image.height == 0:
             logger.error(f"  -> 获取的 ROI 图像尺寸无效 ({roi_image.width}x{roi_image.height})。")
             return None, roi_image # 返回无效图像供调试

        # 2. 对 ROI 图像执行 OCR 获取详细结果
        ocr_details = self._ocr_image_region_with_boxes(roi_image)
        if not ocr_details:
            logger.warning("  -> 在 ROI 内未识别到任何文本节点。")
            # 即使没有文本，也可能需要保存调试图像
            if debug_filename:
                try:
                    import os
                    os.makedirs(os.path.dirname(debug_filename), exist_ok=True)
                    roi_image.save(debug_filename)
                    logger.info(f"  -> (无文本) 调试图像已保存至 {debug_filename}")
                except Exception as save_e:
                    logger.warning(f"  -> 警告：保存 (无文本) 调试图像 '{debug_filename}' 失败: {save_e}")
            return None, roi_image # 没有找到节点，但返回 ROI 图像

        # 3. 处理 OCR 结果，计算相对坐标和中心点
        processed_nodes = []
        roi_width, roi_height = roi_image.size

        for i, detail in enumerate(ocr_details):
            try:
                bbox_abs = detail['bbox'] # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]

                # 计算最小外接矩形 (min_x, min_y, max_x, max_y)
                all_x = [int(p[0]) for p in bbox_abs]
                all_y = [int(p[1]) for p in bbox_abs]
                min_x, min_y = min(all_x), min(all_y)
                max_x, max_y = max(all_x), max(all_y)

                # 边界钳制 (确保在 ROI 图像内)
                min_x = max(0, min_x)
                min_y = max(0, min_y)
                max_x = min(roi_width, max_x)
                max_y = min(roi_height, max_y)

                if min_x >= max_x or min_y >= max_y:
                     logger.warning(f"  -> 跳过无效边界框: text='{detail['text']}', box=({min_x},{min_y},{max_x},{max_y})")
                     continue # 跳过无效的框

                # 计算相对于 ROI 的相对坐标 (0.0 - 1.0)
                rel_x = min_x / roi_width
                rel_y = min_y / roi_height
                rel_w = (max_x - min_x) / roi_width
                rel_h = (max_y - min_y) / roi_height

                # 计算相对于 ROI 的中心点相对坐标
                center_rel_x = (min_x + max_x) / 2 / roi_width
                center_rel_y = (min_y + max_y) / 2 / roi_height

                node_data = {
                    'index': i + 1, # 1-based index
                    'text': detail['text'],
                    'bbox_roi_abs': bbox_abs, # 保留原始像素坐标
                    'bbox_roi_rel': (rel_x, rel_y, rel_w, rel_h),
                    'center_roi_rel': (center_rel_x, center_rel_y),
                    'score': detail['score']
                }
                processed_nodes.append(node_data)

            except Exception as calc_e:
                logger.error(f"  -> 处理节点 '{detail.get('text', 'N/A')}' 的边界框时出错: {calc_e}", exc_info=True)
                continue # 跳过处理出错的节点


        if not processed_nodes:
             logger.warning("  -> 处理后无有效节点。")
             return None, roi_image

        logger.info(f"  -> 成功处理 {len(processed_nodes)} 个节点。")
        return processed_nodes, roi_image

    def handle_chat_message(self, chat_message: str):
        """
        处理从 LLM 响应中提取的 <chat> 内容。
        目前只是记录日志，将来可以扩展为显示、朗读等。

        Args:
            chat_message: 从 <chat> 标签中提取的字符串内容。
        """
        logger.info(f"主播消息: {chat_message}")
        # 可以在这里添加其他处理逻辑，例如：
        # - self.ui_handler.display_chat(chat_message)
        # - self.tts_engine.speak(chat_message)

    def ask_llm(self, prompt: str, history_type: Optional[str] = None) -> Optional[str]:
        """
        向 LLM 发送请求（带可选历史记录）并获取响应。
        自动将用户提示和 LLM 响应添加到指定的历史记录中。
        解析 LLM 响应，将 <chat> 内容传递给 handle_chat_message 处理，
        并仅返回 <choice> 标签内的内容。

        Args:
            prompt (str): 当前的用户提示。
            history_type (Optional[str]): 要使用的历史记录类型 ('map' 或 'combat')。
                                         如果为 None，则不使用历史记录。

        Returns:
            Optional[str]: LLM 响应中 <choice> 标签内的内容，如果未找到或出错则返回 None。
        """
        current_history = []
        if history_type:
            current_history = self.get_history(history_type)
            # logger.debug(f"  -> 使用 '{history_type}' 历史记录 (长度: {len(current_history)}) 进行 LLM 调用。")

        # 调用 LLMClient 的 generate 方法，传递历史记录
        full_response = self.llm_client.generate(prompt, history=current_history)

        # 如果成功获取响应，并且指定了历史类型，则将 *完整* 问答对添加到历史记录
        if full_response is not None and history_type:
            self.add_to_history(history_type, "user", prompt)
            self.add_to_history(history_type, "assistant", full_response) # 记录完整响应

        choice_content: Optional[str] = None
        chat_content: Optional[str] = None

        # 解析响应以提取 <choice> 和 <chat> 内容
        if full_response:
            # 提取 <choice> 内容
            choice_match = re.search(r'<choice>(.*?)</choice>', full_response, re.DOTALL)
            if choice_match:
                choice_content = choice_match.group(1).strip()
                logger.info(f"  -> 从 LLM 响应中提取的 Choice: '{choice_content}'")
            else:
                logger.warning(f"  -> 未能在 LLM 响应中找到 <choice> 标签。")

            # 提取 <chat> 内容
            chat_match = re.search(r'<chat>(.*?)</chat>', full_response, re.DOTALL)
            if chat_match:
                chat_content = chat_match.group(1).strip()
                # 调用新方法处理 chat 内容
                self.handle_chat_message(chat_content)
            else:
                # 如果需要，可以记录未找到 chat 标签的警告
                logger.debug(f"  -> 未能在 LLM 响应中找到 <chat> 标签。") # 使用 debug 级别

            # 检查是否至少提取到了 choice 或 chat，否则记录完整响应以供调试
            if not choice_match and not chat_match:
                 logger.warning(f"  -> LLM 响应中未找到 <choice> 或 <chat> 标签。完整响应: {full_response}")

        else:
            logger.warning("  -> LLM 未返回响应。")

        # 返回提取到的 choice 内容 (可能是 None)
        return choice_content

    def set_last_selected_node(self, node_info: Any):
        """
        存储上一个在地图上选择的节点的信息。

        Args:
            node_info: 节点相关信息 (例如坐标、索引、类型等)。
                       具体类型取决于调用者的需求。
        """
        self._last_selected_node = node_info
        logger.info(f"已存储上一个选择的节点信息: {node_info}")

    def get_last_selected_node(self) -> Optional[Any]:
        """
        获取存储的上一个选择的节点信息。

        Returns:
            Optional[Any]: 存储的节点信息，如果未设置则返回 None。
        """
        return self._last_selected_node

    def _fetch_and_store_screen_dimensions(self):
        """
        内部方法：从 screen_manager 获取屏幕尺寸并存储。
        """
        dimensions = self.screen_manager.get_selected_monitor_dimensions()
        if dimensions:
            self.screen_width, self.screen_height = dimensions
            logger.info(f"屏幕尺寸已获取: {self.screen_width}x{self.screen_height}") # Log fetched dimensions
        else:
            self.screen_width, self.screen_height = None, None # 确保失败时是 None
            logger.warning("获取屏幕尺寸失败。") # Log failure

    def get_screen_dimensions(self) -> Optional[Tuple[int, int]]:
        """
        获取当前选定屏幕的宽度和高度。
        如果尚未获取，则尝试从 ScreenCaptureManager 获取。

        Returns:
            Optional[Tuple[int, int]]: 包含 (宽度, 高度) 的元组，如果无法获取则返回 None。
        """
        # 如果尚未获取或获取失败 (仍为 None)，尝试再次获取
        if self.screen_width is None or self.screen_height is None:
            logger.info("屏幕尺寸尚不可用，尝试获取...")
            self._fetch_and_store_screen_dimensions()

        # 返回存储的值 (可能是 None 如果获取失败)
        if self.screen_width is not None and self.screen_height is not None:
            return (self.screen_width, self.screen_height)
        else:
            logger.error("错误：无法从 ScreenCaptureManager 获取屏幕尺寸。")
            return None

    # --- 共享数据管理 ---

    def update_shared_data(self, key: str, value: Any):
        """
        更新共享数据字典中的值。

        Args:
            key: 要更新的数据的键。
            value: 新的值。

        Returns:
            None
        """
        self.shared_data[key] = value
        logger.debug(f"共享数据已更新: {key} = {value}") # 可选的调试信息

    def get_shared_data(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        """
        从共享数据字典中获取值。

        Args:
            key: 要获取的数据的键。
            default: 如果键不存在时返回的默认值 (默认为 None)。

        Returns:
            对应键的值，如果键不存在则返回 default 值。
        """
        return self.shared_data.get(key, default)

    def _calculate_absolute_roi(self, image: Image.Image, relative_coords: Tuple[float, float, float, float]) -> Optional[Tuple[int, int, int, int]]:
        """计算相对坐标对应的绝对像素坐标 (left, top, right, bottom)。"""
        screen_dims = self.get_screen_dimensions()
        if screen_dims is None:
            logger.error("  -> 错误：无法获取用于 ROI 计算的屏幕尺寸。")
            return None
        screen_width, screen_height = screen_dims

        rel_left, rel_top, rel_width, rel_height = relative_coords
        left = int(image.width * rel_left)
        top = int(image.height * rel_top)
        right = int(image.width * (rel_left + rel_width))
        bottom = int(image.height * (rel_top + rel_height))

        # 边界检查
        left = max(0, left)
        top = max(0, top)
        # 使用 image 尺寸进行右下边界检查更安全，因为截图尺寸可能与屏幕尺寸不完全一致
        right = min(image.width, right)
        bottom = min(image.height, bottom)


        if left >= right or top >= bottom:
            logger.error(f"  -> 错误：计算出的裁剪区域无效 ({left},{top},{right},{bottom})。请检查相对值。")
            return None

        logger.debug(f"  -> 计算出的绝对 ROI: ({left}, {top}, {right}, {bottom})") # Use debug for potentially frequent logs
        return left, top, right, bottom

    def _crop_image_roi(self, image: Image.Image, absolute_roi: Tuple[int, int, int, int], debug_filename: Optional[str] = None) -> Optional[Image.Image]:
        """根据绝对坐标裁剪图像区域。"""
        try:
            roi_image_pil = image.crop(absolute_roi)
            if debug_filename:
                try:
                    # Ensure directory exists before saving
                    import os
                    os.makedirs(os.path.dirname(debug_filename), exist_ok=True)
                    roi_image_pil.save(debug_filename)
                    logger.info(f"  -> 调试图像已保存至 {debug_filename}")
                except Exception as save_e:
                    logger.warning(f"  -> 警告：保存调试图像 '{debug_filename}' 失败: {save_e}")
            return roi_image_pil
        except Exception as e:
            logger.error(f"  -> 裁剪图像区域 {absolute_roi} 时出错: {e}", exc_info=True)
            return None

    def _ocr_image_region(self, roi_image: Image.Image) -> Tuple[Optional[str], Optional[List[Tuple[int, str]]]]:
        """
        对指定的图像区域执行 OCR，并返回处理后的文本及带索引的识别结果。

        Args:
            roi_image: 要识别的 PIL 图像区域。

        Returns:
            Tuple[Optional[str], Optional[List[Tuple[int, str]]]]:
            一个元组，包含：
            - 第一个元素：识别到的所有文本拼接成的字符串 (如果失败则为 None)。
            - 第二个元素：一个列表，包含 (索引, 识别文本片段) 的元组 (如果失败则为 None)。索引从 1 开始。
        """
        ocr_engine = self.get_ocr_engine()
        if ocr_engine is None:
            logger.error("  -> 错误：OCR 引擎不可用于识别。")
            return None, None

        try:
            # 转换为 OCR 格式 (BGR)
            roi_image_cv = cv2.cvtColor(np.array(roi_image), cv2.COLOR_RGB2BGR)

            # OCR 识别
            ocr_result = ocr_engine.ocr(roi_image_cv, cls=True)
            logger.info(f"  -> OCR 原始结果: {ocr_result}") # Debug 输出

            extracted_texts = []
            indexed_results: List[Tuple[int, str]] = []
            current_index = 1

            if ocr_result and ocr_result[0] is not None:
                 for line in ocr_result:
                    if line:
                        # PaddleOCR v3+ 返回 List[List[Any]]
                        # 每个内部列表代表一个检测到的文本行，包含 [bbox, (text, score)]
                        # PaddleOCR v2 可能返回 List[Tuple[bbox, Tuple[str, float]]]
                        # 我们需要处理这两种可能（尽管示例代码似乎是 v3+ 格式）
                        # 假设 ocr_result 是 List[List[Tuple[List[List[int]], Tuple[str, float]]]] 或类似结构
                        for detection_info in line: # 遍历行中的每个检测结果
                            text = ""
                            # 检查常见的 PaddleOCR 输出格式
                            if isinstance(detection_info, (list, tuple)) and len(detection_info) == 2:
                                # 格式: [bbox, (text, score)] or (bbox, (text, score))
                                text_info = detection_info[1]
                                if isinstance(text_info, (list, tuple)) and len(text_info) == 2:
                                    text = text_info[0]
                                    # score = text_info[1] # score 未使用，但可以获取
                            elif isinstance(detection_info, dict) and 'text' in detection_info:
                                # 某些版本的OCR库可能返回字典
                                text = detection_info['text']

                            if text: # 确保提取到了文本
                                extracted_texts.append(text)
                                indexed_results.append((current_index, text))
                                current_index += 1
                            else:
                                logger.warning(f"  -> 无法从检测结果中提取文本: {detection_info}")


            recognized_text = " ".join(extracted_texts).strip()
            logger.info(f"  -> 识别到的文本: '{recognized_text}'")
            logger.info(f"  -> 带索引的识别结果: {indexed_results}")
            return recognized_text, indexed_results
        except Exception as e:
            logger.error(f"  -> OCR 过程中出错: {e}", exc_info=True)
            return None, None

    def get_image_in_relative_roi(
        self,
        relative_coords: Tuple[float, float, float, float],
        debug_filename: Optional[str] = None
    ) -> Optional[Image.Image]:
        """
        获取相对坐标定义的屏幕区域的图像。
        封装了截图、坐标计算和裁剪的步骤。

        Args:
            relative_coords: 包含 (left, top, width, height) 相对比例的元组。
            debug_filename: (可选) 保存裁剪区域图像的调试文件名。

        Returns:
            Optional[Image.Image]: 裁剪后的 PIL 图像对象，如果任何步骤失败则返回 None。
        """
        # 1. 获取截图
        now_frame = self.get_screenshot()
        if now_frame is None:
            logger.error("  -> 错误：获取屏幕截图失败。")
            return None

        # 2. 计算绝对坐标
        absolute_roi = self._calculate_absolute_roi(now_frame, relative_coords)
        if absolute_roi is None:
            # 错误已在 _calculate_absolute_roi 中记录
            return None

        # 3. 裁剪图像
        roi_image = self._crop_image_roi(now_frame, absolute_roi, debug_filename)
        # _crop_image_roi 会在失败时返回 None
        return roi_image

    def recognize_text_in_relative_roi(
        self,
        relative_coords: Tuple[float, float, float, float],
        debug_filename: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[List[Tuple[int, str]]]]: # 修改返回值类型
        """
        识别相对坐标定义的屏幕区域内的文本。
        封装了截图、坐标计算、裁剪和 OCR 的步骤。
        现在返回识别的文本和带索引的结果列表。

        Args:
            relative_coords: 包含 (left, top, width, height) 相对比例的元组。
            debug_filename: (可选) 保存裁剪区域图像的调试文件名。

        Returns:
            Tuple[Optional[str], Optional[List[Tuple[int, str]]]]:
            包含 (识别出的文本字符串, 带索引的结果列表) 的元组，如果任何步骤失败则返回 (None, None)。
        """
        # 1. 获取截图
        now_frame = self.get_screenshot()
        if now_frame is None:
            logger.error("  -> 错误：获取屏幕截图失败。")
            return None, None

        # 2. 计算绝对坐标
        absolute_roi = self._calculate_absolute_roi(now_frame, relative_coords)
        if absolute_roi is None:
            # 错误已在 _calculate_absolute_roi 中记录
            return None, None

        # 3. 裁剪图像
        roi_image = self._crop_image_roi(now_frame, absolute_roi, debug_filename)
        if roi_image is None:
            # 错误已在 _crop_image_roi 中记录
            return None, None

        # 4. OCR 识别 (调用修改后的方法)
        recognized_text, indexed_results = self._ocr_image_region(roi_image)
        # _ocr_image_region 会在失败时返回 (None, None)，成功时返回 (str, list)
        return recognized_text, indexed_results

    def recognize_text_in_relative_roi_and_ask_llm(
        self,
        relative_coords: Tuple[float, float, float, float],
        prompt_template: str,
        knowledge_category: Optional[str] = None, # <-- New parameter
        debug_filename: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        识别相对坐标定义的屏幕区域内的文本，并基于识别结果询问 LLM。
        如果提供了 knowledge_category，会尝试从 game_knowledge 中查找描述
        并将其附加到发送给 LLM 的文本中。

        Args:
            relative_coords: 包含 (left, top, width, height) 相对比例的元组。
            prompt_template: 用于构建 LLM 提示的模板字符串，应包含 '{text}'
                               或 '{indexed_text}' 占位符。
            knowledge_category: (可选) 要在 self.game_knowledge 中查找的知识类别键
                                (例如 'cards', 'nodes', 'blessings')。
            debug_filename: (可选) 保存裁剪区域图像的调试文件名。

        Returns:
            Tuple[Optional[str], Optional[str]]:
                包含 (识别出的文本 [可能带描述], LLM决策) 的元组。
                注意：返回的第一个元素是用于生成 Prompt 的文本（可能已包含描述）。
        """
        recognized_text: Optional[str] = None
        indexed_results: Optional[List[Tuple[int, str]]] = None
        llm_decision: Optional[str] = None
        text_for_prompt: Optional[str] = None # Text actually sent to LLM
        indexed_text_for_prompt: Optional[str] = None # Indexed text sent to LLM

        # 1. 获取截图
        now_frame = self.get_screenshot()
        if now_frame is None:
            logger.error("  -> 错误：获取屏幕截图失败。")
            return None, None

        # 2. 计算绝对坐标
        absolute_roi = self._calculate_absolute_roi(now_frame, relative_coords)
        if absolute_roi is None:
            return None, None

        # 3. 裁剪图像
        roi_image = self._crop_image_roi(now_frame, absolute_roi, debug_filename)
        if roi_image is None:
            return None, None

        # 4. OCR 识别
        recognized_text, indexed_results = self._ocr_image_region(roi_image)

        # 5. (如果需要) 结合知识库增强文本
        if recognized_text is not None and indexed_results is not None:
            text_for_prompt = recognized_text # Default to original text
            indexed_text_for_prompt = "\n".join([f"{idx}: {txt}" for idx, txt in indexed_results]) if indexed_results else ""

            # --- Knowledge Integration Start ---
            if knowledge_category and self.game_knowledge:
                knowledge_dict = self.game_knowledge.get(knowledge_category, {})
                if knowledge_dict: # Only proceed if category exists and has content
                    enhanced_text_parts = []
                    enhanced_indexed_results_formatted = []
                    logger.debug(f"  -> Enhancing text with knowledge from category: {knowledge_category}")

                    for idx, text_item in indexed_results:
                        clean_text_item = text_item.strip()
                        description = "未知" # Default description

                        # Determine the description based on the knowledge category structure
                        item_data = knowledge_dict.get(clean_text_item)

                        if item_data:
                            if isinstance(item_data, dict):
                                # Try common keys for description
                                description = item_data.get('description', item_data.get('quote', '无描述'))
                            elif isinstance(item_data, str):
                                # If the value itself is the description (like in 'blessings')
                                description = item_data
                            else:
                                logger.warning(f"  -> Unexpected data type for knowledge key '{clean_text_item}' in category '{knowledge_category}': {type(item_data)}")
                        else:
                             logger.debug(f"  -> Knowledge key '{clean_text_item}' not found in category '{knowledge_category}'.")


                        enhanced_text = f"{text_item} ({description})" # Use original text_item + desc
                        enhanced_text_parts.append(enhanced_text)
                        enhanced_indexed_results_formatted.append(f"{idx}: {enhanced_text}")

                    if enhanced_text_parts: # Check if any enhancement happened
                        text_for_prompt = " ".join(enhanced_text_parts) # Update the text used for the prompt
                        indexed_text_for_prompt = "\n".join(enhanced_indexed_results_formatted) # Update indexed text
                        logger.debug(f"  -> Enhanced text for prompt: {text_for_prompt}")
            # --- Knowledge Integration End ---

            # 6. 构建 Prompt 并询问 LLM (using text_for_prompt)
            try:
                # Prepare format dictionary using potentially enhanced text
                format_dict = {
                    'text': text_for_prompt,
                    'indexed_text': indexed_text_for_prompt
                }
                # Use .format_map to allow templates to use only needed placeholders
                prompt = prompt_template.format_map(format_dict)

                logger.info(f"  -> 使用 Prompt 询问 LLM: \"{prompt}\"")
                # Pass history_type if needed, maybe add as parameter? For now, default or none.
                llm_decision = self.ask_llm(prompt, history_type='map')
                if llm_decision:
                    logger.info(f"  -> LLM 决策: '{llm_decision}'")
                else:
                    logger.warning("  -> LLM 决策失败或返回空。")
            except KeyError as e:
                logger.error(f"  -> 错误：prompt_template 缺少必要的占位符 (例如 '{{text}}' 或 '{{indexed_text}}'): {e}")
                # LLM 失败，但返回用于 Prompt 的文本
                return text_for_prompt, None
            except Exception as e:
                logger.error(f"  -> 询问 LLM 时出错: {e}", exc_info=True)
                 # LLM 失败，但返回用于 Prompt 的文本
                return text_for_prompt, None
        else:
             logger.warning("  -> OCR 失败或未识别到文本，无法格式化 Prompt 或询问 LLM。")
             # Decide if you want to call LLM with a generic failure message
             # llm_decision = self.ask_llm("OCR failed for the expected region. What should I do?")
             # Return None for text if OCR failed, or empty string? Let's return None.
             return None, None

        # 返回用于 Prompt 的文本 (可能带描述) 和 LLM 决策
        return text_for_prompt, llm_decision