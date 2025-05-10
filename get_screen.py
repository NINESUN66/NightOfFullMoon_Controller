import mss
import mss.tools
from PIL import Image
import sys
import threading
from typing import Optional, Tuple, Dict
import logging
logger = logging.getLogger(__name__)

class ScreenCaptureManager:
    """
    单例模式实现的屏幕捕捉管理器。
    能够列出屏幕、选择屏幕、截取指定屏幕的帧画面，并返回最新截取的帧。
    """
    _instance = None
    _initialized = False # 标记以确保 __init__ 逻辑只运行一次
    _lock = threading.Lock() # 可选：用于线程安全的锁

    def __new__(cls, *args, **kwargs):
        """
        实现单例模式的核心方法。
        如果实例不存在，则创建一个新实例；否则返回现有实例。
        """
        if cls._instance is None:
            # 使用锁防止多线程环境下的竞争条件
            with cls._lock:
                # 在锁内进行双重检查
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        初始化方法。仅在第一次创建实例时执行。
        负责初始化 mss 并引导用户选择要捕捉的屏幕。
        """
        # 仅运行一次初始化逻辑
        if self._initialized:
            return

        # 在关键的初始化阶段使用锁
        with self._lock:
            if self._initialized: # 在锁内进行双重检查
                return

            self._sct = None
            self._selected_monitor_index = None
            self._current_frame = None # 存储最新捕获的帧 (Pillow Image)

            try:
                self._sct = mss.mss()
            except mss.ScreenShotError as e:
                logger.critical(f"初始化 mss 时出错: {e}") # 对致命的初始化错误使用 critical
                logger.critical("无法初始化屏幕捕捉。正在退出。")
                sys.exit(1)
            except Exception as e:
                logger.critical(f"mss 初始化期间发生意外错误: {e}", exc_info=True) # 使用 critical 并记录异常
                logger.critical("正在退出。")
                sys.exit(1)

            self._select_monitor_interactively()

            self._initialized = True
            logger.info("ScreenCaptureManager 初始化成功。")

    def get_selected_monitor_info(self) -> Optional[Dict[str, int]]:
        """
        返回选定监视器的完整信息（包括偏移量）。

        Returns:
            Optional[Dict[str, int]]: 包含 'width', 'height', 'top', 'left' 的字典，
                                     如果未选择监视器或出错则返回 None。
        """
        if self._selected_monitor_index is None or not self._sct:
            logger.error("错误：未选择监视器或 mss 未初始化。")
            return None
        try:
            # 直接返回监视器信息字典的副本
            monitor_info = self._sct.monitors[self._selected_monitor_index].copy()
            # 确保包含必要的键 (mss 通常会提供)
            if all(k in monitor_info for k in ['width', 'height', 'top', 'left']):
                return monitor_info
            else:
                logger.error(f"错误：监视器 {self._selected_monitor_index} 的信息不完整。")
                return None
        except IndexError:
            logger.error(f"错误：无效的监视器索引 {self._selected_monitor_index}。")
            return None
        except Exception as e:
            logger.error(f"获取监视器信息时发生意外错误: {e}", exc_info=True)
            return None

    def _select_monitor_interactively(self):
        """
        交互式地列出可用屏幕并让用户选择。
        """
        monitors = self._sct.monitors
        logger.info("\n可用监视器:") # 使用 info 进行列表显示
        # mss.monitors[0] 是包含所有显示器的虚拟屏幕。
        # 后续索引 (1, 2, ...) 是单个物理监视器。
        # 我们引导用户选择一个物理监视器 (索引 > 0)。
        for i, monitor in enumerate(monitors):
            if i == 0:
                logger.info(f"{i}: 虚拟桌面 (所有屏幕)") # 使用 info
            else:
                logger.info(f"{i}: 监视器 {i} (尺寸: {monitor['width']}x{monitor['height']}, 顶部: {monitor['top']}, 左侧: {monitor['left']})") # 使用 info

        valid_choice = False
        while not valid_choice:
            try:
                # 提示选择物理监视器 (索引 > 0)
                # 输入提示保留，但周围的消息使用日志记录
                choice = input(f"请输入要捕捉的监视器编号 (物理监视器为 1-{len(monitors)-1}): ")
                monitor_index = int(choice)

                # 验证选择：必须是物理监视器索引 (1 到 len(monitors)-1)
                if 1 <= monitor_index < len(monitors):
                     self._selected_monitor_index = monitor_index
                     logger.info(f"已选择监视器: {monitor_index}") # 使用 info 确认选择
                     valid_choice = True
                elif monitor_index == 0:
                     logger.warning("选择虚拟桌面 (0) 会捕捉所有屏幕。请选择一个具体的物理监视器 (1 或更高)。") # 使用 warning 进行指导
                     # 如果用户选择 0，继续询问，因为要求是“指定的屏幕”
                     continue
                else:
                    logger.warning("无效的监视器编号。请重试。") # 对无效输入使用 warning
            except ValueError:
                logger.warning("无效输入。请输入一个数字。") # 对无效输入类型使用 warning
            except EOFError: # 处理输入流意外关闭的情况
                logger.critical("\n输入流已关闭。无法获取监视器选择。正在退出。") # 对致命的输入错误使用 critical
                sys.exit(1)
            except KeyboardInterrupt: # 处理输入期间的 Ctrl+C
                logger.info("\n监视器选择已取消。正在退出。") # 对用户取消操作使用 info
                sys.exit(0)

    def capture_frame(self):
        """
        从选定的屏幕截取一帧画面并更新内部存储。
        返回截取到的 Pillow Image 对象，如果失败则返回 None。
        """
        if self._selected_monitor_index is None:
             logger.error("错误：初始化期间未选择监视器。") # 对缺少先决条件使用 error
             return None

        try:
            # grab() 使用 monitor=N (N>0) 定位第 N 个物理监视器
            # 从列表中访问正确的监视器字典
            monitor_info = self._sct.monitors[self._selected_monitor_index]
            sct_img = self._sct.grab(monitor_info)

            # 将 mss 截图对象转换为 PIL Image
            # mss 提供原始像素和尺寸，Image.frombytes 处理转换
            img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)

            # 存储最新帧
            self._current_frame = img
            return img
        except mss.ScreenShotError as e:
            logger.error(f"捕捉屏幕时出错: {e}") # 对捕捉失败使用 error
            self._current_frame = None # 出错时清除可能存在的旧帧
            return None
        except Exception as e:
            logger.error(f"捕捉期间发生意外错误: {e}", exc_info=True) # 使用 error 并记录异常
            self._current_frame = None
            return None

    def get_current_frame(self):
        """
        返回最近一次成功截取到的帧画面 (Pillow Image 对象)。
        如果尚未截取任何帧，则返回 None。
        """
        if self._current_frame is None:
            logger.warning("尚未捕捉任何帧。请先调用 capture_frame()。") # 对预期的缺失数据使用 warning
        return self._current_frame

    def get_selected_monitor_dimensions(self) -> Optional[Tuple[int, int]]:
        """
        返回选定监视器的宽度和高度。

        Returns:
            Optional[tuple[int, int]]: 包含 (宽度, 高度) 的元组，如果未选择监视器或出错则返回 None。
        """
        if self._selected_monitor_index is None or not self._sct:
            logger.error("错误：未选择监视器或 mss 未初始化。") # 对缺少先决条件使用 error
            return None
        try:
            monitor_info = self._sct.monitors[self._selected_monitor_index]
            return (monitor_info['width'], monitor_info['height'])
        except IndexError:
            logger.error(f"错误：无效的监视器索引 {self._selected_monitor_index}。") # 对无效索引使用 error
            return None
        except Exception as e:
            logger.error(f"获取监视器尺寸时发生意外错误: {e}", exc_info=True) # 使用 error 并记录异常
            return None

    # 可选：用于 mss 资源清理的上下文管理
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, '_sct') and self._sct:
             self._sct.close() # 释放 mss 资源
             logger.info("mss 资源已关闭。") # 记录资源清理