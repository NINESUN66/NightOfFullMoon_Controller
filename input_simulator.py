import pydirectinput
import time
from typing import Optional, Tuple
import logging
import os # 导入 os 模块用于创建目录
from datetime import datetime # 导入 datetime 用于生成唯一文件名
import pyautogui 

logger = logging.getLogger(__name__)

# 导入 GameContext 仅为了类型提示，避免循环导入
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from game_context import GameContext
    from PIL import Image # 导入 Image 用于类型提示

class InputSimulator:
    """封装模拟输入操作（鼠标、键盘）。"""

    def __init__(self, context: Optional['GameContext'] = None, debug_image_dir: str = "images/clicks"):
        """
        初始化 InputSimulator。

        Args:
            context: GameContext 实例，用于获取屏幕尺寸以进行相对坐标点击。
            debug_image_dir: 保存点击调试图像的目录。
        """
        self.context = context
        self.debug_image_dir = debug_image_dir
        # 确保调试图像目录存在
        os.makedirs(self.debug_image_dir, exist_ok=True)
        pydirectinput.PAUSE = 0.05 # 每次操作后的默认小延迟
        logger.info("输入模拟器已初始化 (使用 pydirectinput)。")
        logger.info(f"点击调试图像将保存到: {os.path.abspath(self.debug_image_dir)}")


    def set_context(self, context: 'GameContext'):
        """允许在初始化后设置 GameContext。"""
        self.context = context
        logger.info("已为输入模拟器设置 GameContext。")

    def _get_global_coords_from_relative(self, rel_x: float, rel_y: float) -> Optional[Tuple[int, int]]:
        """
        内部辅助函数：将相对于选定监视器的相对坐标转换为全局屏幕坐标。
        """
        if not self.context:
            logger.error("  -> 错误：未在 InputSimulator 中设置 GameContext。")
            return None
        # 获取选定监视器的信息，包括尺寸和偏移量
        monitor_info = self.context.screen_manager.get_selected_monitor_info()
        if not monitor_info:
            logger.error("  -> 错误：无法获取选定监视器的信息。")
            return None

        monitor_width = monitor_info['width']
        monitor_height = monitor_info['height']
        monitor_left = monitor_info['left']
        monitor_top = monitor_info['top']

        # 1. 计算在监视器内部的局部坐标 (相对于监视器左上角)
        local_x = int(monitor_width * rel_x)
        local_y = int(monitor_height * rel_y)

        # 2. 将局部坐标转换为全局坐标 (加上监视器的偏移量)
        global_x = monitor_left + local_x
        global_y = monitor_top + local_y

        logger.debug(f"  -> 相对坐标 ({rel_x:.3f}, {rel_y:.3f}) -> "
                     f"监视器局部坐标 ({local_x}, {local_y}) -> "
                     f"全局坐标 ({global_x}, {global_y})")
        return global_x, global_y

    def _save_click_debug_image(self, global_x: int, global_y: int, screenshot: 'Image.Image', monitor_info: dict, crop_size: int = 100):
        """
        在点击位置附近截取并保存调试图像。

        Args:
            global_x: 点击的全局 X 坐标。
            global_y: 点击的全局 Y 坐标。
            screenshot: 已捕获的选定监视器的截图 (PIL Image)。
            monitor_info: 选定监视器的信息字典 (包含 left, top, width, height)。
            crop_size: 裁剪区域的边长（像素）。
        """
        try:
            monitor_left = monitor_info['left']
            monitor_top = monitor_info['top']
            monitor_width = monitor_info['width']
            monitor_height = monitor_info['height']

            # 将全局点击坐标转换为截图内的局部坐标
            local_x = global_x - monitor_left
            local_y = global_y - monitor_top

            # 计算裁剪框 (左上角和右下角)
            half_crop = crop_size // 2
            left = max(0, local_x - half_crop)
            top = max(0, local_y - half_crop)
            # 确保右下角不超过截图边界
            right = min(monitor_width, local_x + half_crop)
            bottom = min(monitor_height, local_y + half_crop)

            if left >= right or top >= bottom:
                 logger.warning(f"  -> 无法为点击 ({global_x}, {global_y}) 创建有效的裁剪区域 ({left},{top},{right},{bottom})。")
                 return

            # 裁剪图像
            cropped_image = screenshot.crop((left, top, right, bottom))

            # 添加一个标记点在点击位置 (相对于裁剪区域)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(cropped_image)
            # 计算标记点在裁剪图中的坐标
            mark_x = local_x - left
            mark_y = local_y - top
            # 画一个小红叉或圆点
            marker_size = 3
            draw.line([(mark_x - marker_size, mark_y), (mark_x + marker_size, mark_y)], fill="red", width=1)
            draw.line([(mark_x, mark_y - marker_size), (mark_x, mark_y + marker_size)], fill="red", width=1)
            # 或者画一个点: draw.ellipse([(mark_x-1, mark_y-1), (mark_x+1, mark_y+1)], fill="red")


            # 生成唯一文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = os.path.join(self.debug_image_dir, f"click_{timestamp}_at_({global_x},{global_y}).png")

            # 保存图像
            cropped_image.save(filename)
            logger.info(f"  -> 点击位置调试图像已保存: {filename}")

        except Exception as e:
            logger.error(f"  -> 保存点击调试图像时出错: {e}", exc_info=True)


    def click(self, x: int, y: int, duration: float = 0.1, button: str = 'left', save_debug_image: bool = True):
        """
        在全局屏幕坐标 (x, y) 处模拟鼠标点击。
        现在 x, y 被视为全局坐标。

        Args:
            x: 全局屏幕 X 坐标。
            y: 全局屏幕 Y 坐标。
            duration: 点击持续时间（秒）。
            button: 'left', 'right', 'middle'。
            save_debug_image: 是否保存点击位置的调试图像。
        """
        screenshot = None
        monitor_info = None
        if save_debug_image and self.context:
            # 尝试获取当前帧和监视器信息以供截图保存
            screenshot = self.context.get_screenshot() # 获取选定监视器的截图
            monitor_info = self.context.screen_manager.get_selected_monitor_info()
            if not screenshot or not monitor_info:
                logger.warning("  -> 无法获取截图或监视器信息，跳过保存调试图像。")
                save_debug_image = False # 无法保存，禁用

        logger.info(f"  -> 模拟点击全局坐标 ({x}, {y})")
        try:
            pydirectinput.moveTo(x, y)
            time.sleep(0.01) # 短暂暂停确保移动完成

            # 在按下鼠标前保存截图（如果需要）
            if save_debug_image and screenshot and monitor_info:
                 self._save_click_debug_image(x, y, screenshot, monitor_info)

            pydirectinput.mouseDown(button=button)
            time.sleep(duration) # 控制点击时长
            pydirectinput.mouseUp(button=button)
        except Exception as e:
            logger.error(f"  -> 模拟全局坐标点击时出错: {e}", exc_info=True)

    def click_relative(self, rel_x: float, rel_y: float, duration: float = 0.1, button: str = 'left', save_debug_image: bool = True) -> bool:
        """
        在相对于选定监视器的相对坐标 (rel_x, rel_y) 处模拟鼠标点击。
        """
        # 计算全局坐标
        global_coords = self._get_global_coords_from_relative(rel_x, rel_y)
        if not global_coords:
            return False # 错误已在 _get_global_coords_from_relative 中记录

        global_x, global_y = global_coords
        # 调用 click 方法，传递全局坐标
        self.click(global_x, global_y, duration, button, save_debug_image)
        return True

    def drag_relative(self, start_rel_x: float, start_rel_y: float, end_rel_x: float, end_rel_y: float, duration: float = 0.5, button: str = 'left') -> bool:
        """
        模拟鼠标从一个相对坐标点拖动到另一个相对坐标点（使用全局坐标）。
        """
        start_global_coords = self._get_global_coords_from_relative(start_rel_x, start_rel_y)
        end_global_coords = self._get_global_coords_from_relative(end_rel_x, end_rel_y)

        if not start_global_coords or not end_global_coords:
            logger.error("  -> 错误：无法计算拖动的全局坐标。")
            return False

        start_x, start_y = start_global_coords
        end_x, end_y = end_global_coords

        logger.info(f"  -> 模拟拖动从相对 ({start_rel_x:.3f}, {start_rel_y:.3f}) -> 全局 ({start_x}, {start_y})")
        logger.info(f"  ->                到相对 ({end_rel_x:.3f}, {end_rel_y:.3f}) -> 全局 ({end_x}, {end_y})，持续 {duration} 秒")

        try:
            # 1. 移动到起始点 (全局坐标)
            pydirectinput.moveTo(start_x, start_y, duration=0.1)
            time.sleep(0.05)

            # 2. 按下鼠标按钮
            pydirectinput.mouseDown(button=button)
            time.sleep(0.05)

            # 3. 拖动到结束点 (全局坐标)
            pydirectinput.moveTo(end_x, end_y, duration=duration)
            time.sleep(0.05)

            # 4. 释放鼠标按钮
            pydirectinput.mouseUp(button=button)
            logger.info("  -> 拖动模拟完成。")
            return True
        except Exception as e:
            logger.error(f"  -> 模拟拖动时出错: {e}", exc_info=True)
            # 尝试确保鼠标按钮被释放
            try:
                pydirectinput.mouseUp(button=button)
            except Exception as release_e:
                logger.error(f"  -> 拖动出错后尝试释放鼠标按钮时出错: {release_e}", exc_info=True)
            return False


    def choose_level(self, level: int, duration: float = 0.1):
        """
        模拟选择游戏关卡。
        """
        # ... (代码不变, 它调用 click_relative) ...
        if not (1 <= level <= 3):
            logger.error("  -> 错误：关卡编号必须在 1 到 3 之间。")
            return False

        level_coords = {
            1: (0.3, 0.63),  # 左侧
            2: (0.5, 0.63),  # 中间
            3: (0.7, 0.63)   # 右侧
        }
        rel_x, rel_y = level_coords[level]
        logger.info(f"  -> 选择关卡 {level}，相对坐标 ({rel_x:.3f}, {rel_y:.3f})")
        
        self.click_relative(rel_x, rel_y - 0.2, duration=duration, save_debug_image=True)
        self.click_relative(rel_x, rel_y, duration=duration, save_debug_image=True)
        logger.info("  -> 关卡选择完成。")

    def delete_level(self, level: int, duration: float = 0.1):
        """
        模拟删除游戏关卡。
        """
        # ... (代码不变, 它调用 click_relative) ...
        if not (1 <= level <= 3):
            logger.error("  -> 错误：关卡编号必须在 1 到 3 之间。")
            return False

        delete_coords = {
            1: (0.35, 0.24),  # 左侧
            2: (0.56, 0.25),  # 中间
            3: (0.76, 0.25)   # 右侧
        }
        rel_x, rel_y = delete_coords[level]
        logger.info(f"  -> 模拟删除关卡 {level}，相对坐标 ({rel_x:.3f}, {rel_y:.3f})")
        self.click_relative(rel_x, rel_y, duration=duration, save_debug_image=True)
        logger.info("  -> 删除关卡完成。")

    def scroll(self, amount: int):
        """
        模拟鼠标滚轮滚动。
        使用 pyautogui 来实现滚轮模拟，因为 pydirectinput 不支持此功能。
        """
        logger.info(f"  -> 模拟滚动 {amount}")
        try:
            # 使用 pyautogui.scroll 进行滚轮模拟。
            pyautogui.scroll(amount)
            logger.info("  -> 滚动模拟完成。")
            return True
        except Exception as e:
            logger.error(f"  -> 模拟滚动时出错: {e}", exc_info=True)
            return False
