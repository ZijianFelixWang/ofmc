"""
    OFMC: Obsidian-Flavored Markdown to LaTeX Compiler.
    Copyright (C) 2025  Nuaptan F. Evalisk = Z. F. Wang

    This file is part of OFMC.

    OFMC is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published
    by the Free Software Foundation, either version 3 of the License,
    or (at your option) any later version.

    OFMC is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with OFMC. If not, see <https://www.gnu.org/licenses/>.
"""

import re

def fix_markdown_spacing(content: str) -> str:
    """
    一个自定义的 Markdown 预处理器，用于解决布局间距问题。

    它执行两个主要操作，以正确的顺序：
    1. 在特殊标题（如 '**证明:**'）后添加一个空行，前提是后面不是空行。
    2. 在列表项（无序或有序）后添加一个空行，前提是后面紧跟着的不是另一个列表项或空行。
       这个操作能正确处理嵌套的块引用。
    """

    # --- 规则 1: 处理特殊标题 (例如 "**证明:**") (已修正) ---
    # 核心修正：将结尾的匹配从 `\*\*:` 改为 `:\*\*`
    # 同时使用命名捕获组以提高可读性和健壮性
    header_pattern = re.compile(
        r"^(?P<header>\s*\*\*[^*]+:\*\*\s*)(?P<newline>\r?\n)(?!\s*\n|$)",
        flags=re.MULTILINE
    )
    # 替换逻辑: 保留标题行和它的换行符，再额外添加一个换行符
    content = header_pattern.sub(r"\g<header>\g<newline>\g<newline>", content)


    # --- 规则 2: 处理所有类型的列表项 (工作正常，保持不变) ---
    list_item_pattern = re.compile(r"""
    ^                           # 匹配行的开始
    (                           # 开始捕获组 1: list_item_line (整个列表项所在的行)
        (?P<prefix>(?:>\s*)*)   #   开始命名捕获组 'prefix': 块引用前缀 (0个或多个 '>')
        \s*                     #   可选的前导空格
        (?:[-*+]|\d+\.)          #   列表标记: 匹配 '-', '*', '+' 或 '数字.'
        \s+                     #   列表标记和内容之间的必要空格
        .*                      #   列表项的其余所有内容
    )                           # 结束捕获组 1
    (?P<newline_list>\r?\n)      # 命名捕获组 'newline_list': 列表项的换行符
    (?!                         # 开始负向先行断言 (下一行必须不是...)
        \s*$                    #   ...一个空行或文件末尾
        |                       #   或
        (?P=prefix)             #   ...与之前匹配的相同的前缀
        \s*
        (?:[-*+]|\d+\.)\s+      #   ...另一个列表项
    )
    """, flags=re.MULTILINE | re.VERBOSE)

    content = list_item_pattern.sub(
        lambda m: f"{m.group(1)}{m.group('newline_list')}{m.group('prefix')}{m.group('newline_list')}",
        content
    )

    return content

def preprocess_book_references(markdown_text: str) -> str:
    """
    Finds custom book reference wikilinks and converts them into a
    highlighted format.

    This pre-processor specifically targets links of the format:
    [[Book Titles#^SomeID]]
    where 'SomeID' is any sequence of non-whitespace characters.

    It replaces them with:
    ==(Book with id: SomeID)==
    """

    # 正则表达式解释:
    # \[\[Book Titles#\^  - 匹配固定的前缀 "[[Book Titles#^"
    #                          注意: [ 需要被转义为 \[
    # (\S+)                - 这是捕获组 1。
    #                          \S  匹配任何非空白字符。
    #                          +   表示匹配一个或多个。
    #                          所以 (\S+) 会捕获像 "IM" 或 "GTM82" 这样的 ID。
    # \]\]                 - 匹配固定的后缀 "]]"
    #                          注意: ] 需要被转义为 \]
    pattern = r"\[\[Book Titles#\^(\S+)\]\]"

    # 替换字符串解释:
    # ==(Book with id: \1)== - 这是一个固定的模板。
    #                          \1 会被替换为正则表达式中第一个捕获组匹配到的内容，
    #                          也就是我们捕获到的那个不含空格的 ID。
    replacement = r"==(Book with id: \1)=="

    # 使用 re.sub 执行全局查找和替换
    return re.sub(pattern, replacement, markdown_text)
