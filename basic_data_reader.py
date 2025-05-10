import subprocess
import time
import os
import logging # 导入 logging

logger = logging.getLogger(__name__) # 获取 logger 实例

class BasicDataReader:
    def __init__(self, executable_path="CE.exe"):
        """
        初始化 BasicDataReader 类。

        Args:
            executable_path (str): 可执行文件的路径，默认为 "CE.exe"。
        """
        self.executable_path = executable_path
        logger.info(f"BasicDataReader 已初始化，可执行文件路径: {self.executable_path}") # 中文日志

    def _parse_output(self, output_str):
        """
        解析可执行文件的输出字符串，提取键值对。

        Args:
            output_str (str): 可执行文件的标准输出。

        Returns:
            dict: 包含解析后的数据的字典。
        """
        stats = {}
        lines = output_str.strip().split('\n')
        for line in lines:
            line = line.strip()  # 处理可能的前后空格
            if ':' in line:
                key, value = line.split(':', 1)
                try:
                    # 尝试将值转换为整数，如果失败则保留为字符串（例如错误标志）
                    stats[key.strip()] = int(value.strip())
                except ValueError:
                    stats[key.strip()] = value.strip()
        logger.debug(f"解析后的数据: {stats}") # 中文日志
        return stats

    def read_data(self):
        """
        运行可执行文件并读取和解析输出数据。

        Returns:
            dict or None: 如果成功读取并解析数据，则返回包含数据的字典；
                         如果发生错误，则返回 None。
        """
        logger.debug(f"尝试运行可执行文件: {self.executable_path}") # 中文日志
        try:
            result = subprocess.run(
                [self.executable_path],
                capture_output=True,
                text=True,
                check=False, # 不要自动检查返回码，手动处理
                encoding='utf-8',
                errors='ignore', # 忽略解码错误
                timeout=5 # 设置超时时间
            )
            logger.debug(f"可执行文件执行完毕，返回码: {result.returncode}") # 中文日志
            logger.debug(f"可执行文件标准输出:\n{result.stdout}") # 中文日志
            if result.stderr:
                logger.warning(f"可执行文件标准错误:\n{result.stderr}") # 中文日志

        except subprocess.TimeoutExpired:
            logger.error(f"C++ 可执行文件 '{self.executable_path}' 运行超时！") # 中文日志
            return None
        except FileNotFoundError:
            logger.error(f"错误: 在 '{self.executable_path}' 未找到可执行文件") # 中文日志
            return None
        except PermissionError:
             logger.error(f"尝试运行 '{self.executable_path}' 时权限不足。请尝试以管理员身份运行？") # 中文日志
             return None
        except Exception as e:
            logger.error(f"运行子进程时发生意外错误: {e}", exc_info=True) # 中文日志
            return None

        # 检查返回码
        if result.returncode != 0:
            logger.error(f"C++ 可执行文件执行失败，返回码: {result.returncode}") # 中文日志
            # 尝试解析可能的错误信息
            init_error_data = self._parse_output(result.stdout)
            logger.error(f"  来自标准输出的错误详情: {init_error_data}") # 中文日志
            if "init_error_window" in init_error_data:
                logger.error("  (提示: 游戏可能未运行或窗口标题/类名不匹配)") # 中文日志
            elif "init_error_handle" in init_error_data:
                logger.error("  (提示: 可能需要管理员权限来运行 Python 脚本)") # 中文日志
            return None
        else:
            # 成功执行，解析数据
            parsed_data = self._parse_output(result.stdout)
            logger.info("成功从可执行文件读取并解析数据。") # 中文日志
            return parsed_data

if __name__ == "__main__":
    # 配置 logging
    logging.basicConfig(level=logging.INFO, # 设置日志级别
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    reader = BasicDataReader("CE.exe")  # 实例化 BasicDataReader 类

    try:
        while True:
            data = reader.read_data()
            if data:
                print(f"\n--- 更新时间 {time.time()} ---")

                # 打印玩家状态
                if "p_error" not in data:
                    print("玩家状态:")
                    print(f"  HP: {data.get('p_currentHP', 'N/A')}/{data.get('p_maxHP', 'N/A')}")
                    print(f"  职业: {data.get('p_class', 'N/A')}")
                    print(f"  蓝量: {data.get('p_mana', 'N/A')}")
                    print(f"  经验: {data.get('p_experience', 'N/A')}")
                    print(f"  金钱: {data.get('p_money', 'N/A')}")
                    print(f"  抽卡: {data.get('p_cardDraws', 'N/A')}")
                    print(f"  等级: {data.get('p_level', 'N/A')}")
                    print(f"  行动点: {data.get('p_actionPoints', 'N/A')}")
                else:
                    print("玩家状态: 读取失败")

                # 打印战斗状态
                if "c_error" not in data:
                    print("战斗状态:")
                    print(f"  HP: {data.get('c_currentHP', 'N/A')}/{data.get('c_maxHP', 'N/A')}")
                    print(f"  行动点: {data.get('c_actionPoints', 'N/A')}")
                else:
                    print("战斗状态: 读取失败 (或不在战斗中)")

                # 打印敌人状态
                if "e_error" not in data:
                    if data.get('e_maxHP', -1) != -1 or data.get('e_currentHP', -1) != -1:
                        print("敌人状态:")
                        print(f"  HP: {data.get('e_currentHP', 'N/A')}/{data.get('e_maxHP', 'N/A')}")
                else:
                    print("敌人状态: 读取失败 (或不在战斗中)")

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n收到中断，退出...")