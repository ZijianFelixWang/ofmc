# my_sorter.py (Corrected to handle multiple time formats)

import re
from datetime import datetime
from pathlib import Path

# 正则表达式保持不变，因为它能正确提取出时间字符串
METADATA_REGEX = re.compile(r"Created Time:\s*`(.+?)`")

DEFAULT_TIME = datetime.min

def get_sort_key(md_path: Path) -> datetime:
    """
    从 Markdown 文件中读取元数据，解析 'Created Time' 并返回一个 datetime 对象。
    这个版本能够处理多种时间格式。
    """
    try:
        with md_path.open('r', encoding='utf-8', errors='ignore') as f:
            content_head = "".join(f.readline() for _ in range(20))

            match = METADATA_REGEX.search(content_head)
            if match:
                time_str = match.group(1).strip()

                # =====================================================================
                #  核心修正：定义一个格式列表，并逐一尝试
                # =====================================================================
                # 格式1: 带 AM/PM 的 12 小时制
                format_1 = "%m/%d/%Y %I:%M:%S %p"
                # 格式2: 不带 AM/PM 的 24 小时制 (注意这里用 %H 而不是 %I)
                format_2 = "%m/%d/%Y %H:%M:%S"

                for fmt in [format_1, format_2]:
                    try:
                        # 尝试用当前格式解析
                        return datetime.strptime(time_str, fmt)
                    except ValueError:
                        # 如果此格式不匹配，什么也不做，继续尝试下一个
                        continue

                # 如果所有格式都尝试失败，打印警告并继续
                print(f"⚠️  Warning: Could not parse date '{time_str}' for {md_path.name} with any known format.")

    except IOError as e:
        print(f"⚠️  Warning: Could not read file {md_path.name}: {e}")

    # 如果发生任何错误或所有格式都失败，返回默认时间
    return DEFAULT_TIME
