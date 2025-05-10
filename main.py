import time
from typing import Optional
import logging # 导入 logging 模块
import traceback # 确保 traceback 已导入
import json # <--- 添加 json 导入

# --- 导入状态模式相关类 ---
from game_context import GameContext
from states import InitializationState

# --- 导入核心组件 ---
from get_screen import ScreenCaptureManager
from basic_data_reader import BasicDataReader
from llm_client import LLMClient
from input_simulator import InputSimulator


def initialize_game() -> Optional[GameContext]:
    """
    初始化所有必要的组件并创建 GameContext。

    Returns:
        Optional[GameContext]: 如果初始化成功，返回 GameContext 实例；否则返回 None。
    """
    logging.info("--- 初始化游戏组件 ---")
    try:
        # 1. 初始化屏幕捕捉器
        screen_manager = ScreenCaptureManager()
        logging.info("ScreenCaptureManager 初始化成功.")

        # 2. 初始化内存读取器 (根据实际情况修改可执行文件路径)
        # 注意：如果 C++ 程序需要管理员权限，Python 脚本也需要以管理员权限运行
        data_reader = BasicDataReader("CE.exe") # 或者你的 C++ 程序路径
        logging.info("BasicDataReader 初始化成功.")

        # 3. 初始化 LLM 客户端 (配置 API Key 和模型)
        # 建议从环境变量或配置文件读取 API Key
        # TODO: 从配置加载模型名称
        llm_client = LLMClient(model_name="gpt-4o-mini")
        logging.info("LLMClient 初始化成功.")

        # 4. 初始化 OCR 引擎
        ocr_engine = None # 默认无 OCR
        try:
            from paddleocr import PaddleOCR
            # TODO: 从配置加载 OCR 参数
            ocr_engine = PaddleOCR(use_angle_cls=True, lang='ch', use_gpu=True, show_log=False)
            logging.info("PaddleOCR 初始化成功.")
        except ImportError:
            logging.warning("paddleocr 未找到. OCR 功能不可用.")
        except Exception as e:
            logging.error(f"初始化 PaddleOCR 时失败: {e}. OCR 功能不可用.", exc_info=True)


        # 5. 初始化输入模拟器
        input_simulator = InputSimulator() # 创建实例
        logging.info("InputSimulator 初始化成功.")

        # 6. 创建初始状态
        initial_state = InitializationState()
        logging.info(f"初始状态设置为: {type(initial_state).__name__}")

        # 7. 创建并返回 GameContext
        # GameContext 内部会加载 prompt.json
        game_context = GameContext(
            screen_manager=screen_manager,
            data_reader=data_reader,
            ocr_engine=ocr_engine, # 传递可能为 None 的 OCR 引擎
            llm_client=llm_client,
            input_simulator=input_simulator,
            initial_state=initial_state,
            prompt_file="prompt.json" # 确保传递了文件名
        )
        logging.info("--- GameContext 创建成功 ---")
        return game_context

    except Exception as e:
        logging.error(f"初始化时出错: {e}", exc_info=True)
        return None

def main_loop(game_context: GameContext, loop_delay: float = 1.0):
    """
    游戏主循环，不断调用当前状态的处理方法。

    Args:
        game_context: 已初始化的 GameContext 实例。
        loop_delay: 每次循环之间的延迟时间（秒），用于控制执行速度。
    """
    logging.info("\n--- 开始主循环 (Press Ctrl+C to exit) ---")
    try:
        while True:
            # 获取当前状态对象，而不是调用它
            current_state = game_context.current_state
            if current_state:
                logging.info(f"\n--- 当前状态: {type(current_state).__name__} ---")
                current_state.handle() # 调用状态对象的 handle 方法
            else:
                logging.error("错误：无法获取当前游戏状态。")
                return
            # 控制循环速率，避免CPU占用过高
            time.sleep(1) # 暂停1秒
    except KeyboardInterrupt:
        logging.info("\n--- 键盘打断, 正在停止主循环. ---")
    except Exception as e:
        logging.error(f"\n--- 在主循环运行时出现错误: {e} ---", exc_info=True)
    finally:
        logging.info("--- 退出应用中... ---")
        # game_context.cleanup() # 如果 GameContext 有清理方法


def main():
    """
    应用程序入口点。
    """
    # --- 配置日志 ---
    # 创建 logs 目录（如果不存在）
    import os
    if not os.path.exists('logs'):
        os.makedirs('logs')
    log_filename = f'logs/game_agent_{time.strftime("%Y%m%d_%H%M%S")}.log'
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s' # 添加文件名和行号
    logging.basicConfig(
        level=logging.INFO, # 设置日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format=log_format,
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'), # 输出到文件
            logging.StreamHandler() # 同时输出到控制台
        ]
    )
    # -----------------

    logging.info("--- 启动！！！ ---")
    game_context = initialize_game()

    if game_context:
        # --- 在进入主循环前，发送一次性初始化提示 ---
        try:
            init_prompt_data = game_context.prompts.get("initialization", {})
            init_prompt_text = init_prompt_data.get("prompt", "")

            if init_prompt_text and isinstance(init_prompt_text, str):
                logging.info("正在向 LLM 发送一次性初始化提示...")
                # 构建仅包含初始化提示的消息列表
                # 注意：消息格式需符合您的 LLMClient 要求
                initial_messages = [{"role": "user", "content": init_prompt_text}]
                logging.debug(f"发送的初始化消息: {initial_messages}")

                # 调用 LLM 发送
                # 确保 llm_client 存在
                if game_context.llm_client:
                    init_response = game_context.llm_client.generate(prompt=initial_messages[0]['content'])
                    if init_response:
                        logging.info(f"LLM 初始化响应: {init_response}")
                else:
                    logging.error("LLMClient 未在 GameContext 中初始化，无法发送初始化提示。")

            else:
                logging.warning("未找到有效的 'initialization' 提示文本，跳过发送。")

        except AttributeError:
             logging.error("GameContext 对象缺少 'prompts' 或 'llm_client' 属性。请检查 GameContext 初始化。")
        except Exception as e:
            logging.error(f"发送初始化提示给 LLM 时出错: {e}", exc_info=True)
            # 可以选择是否因为此错误而停止程序，这里选择继续

        # --- 启动主循环 ---
        main_loop(game_context, loop_delay=2.0) # 设置循环间隔为 2 秒
    else:
        logging.error("游戏上下文初始化失败，无法启动主循环。")

    logging.info("--- 退出！！！ ---")


if __name__ == "__main__":
    main()