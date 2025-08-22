# utils.py
import re
import unicodedata

def insert_blank_blockquote_lines(text: str) -> str:
    """
    Inserts an empty line between consecutive blockquote lines to ensure
    that multi-line blockquotes are treated as separate paragraphs.
    """
    lines = text.splitlines()
    new_lines = []
    prev_is_blockquote = False

    for line in lines:
        curr_is_blockquote = line.lstrip().startswith('>')

        if prev_is_blockquote and curr_is_blockquote:
            # Insert an empty blockquote line between two blockquote lines
            new_lines.append('>')

        new_lines.append(line)
        prev_is_blockquote = curr_is_blockquote

    return '\n'.join(new_lines)

def demote_headings(latex: str) -> str:
    """
    Converts numbered heading commands to unnumbered (starred) ones
    in embedded LaTeX chunks, to avoid TOC/number pollution.
    """
    return re.sub(
        r'\\(sub)*section(?!\*)(\s*\{)',  # matches \section{ or \subsection{ etc.
        lambda m: f"\\{m.group(1) or ''}section*{m.group(2)}",
        latex
    )

def normalize_unicode(text: str) -> str:
    replacements = {
        '\u202F': ' ',     # narrow no-break space → space
        '\u00A0': ' ',     # no-break space → space
        '\u200B': '',      # zero width space → remove
        '\uFFFC': '',      # object replacement → remove (or '[obj]')
    }
    for bad_char, replacement in replacements.items():
        text = text.replace(bad_char, replacement)
    return text

def fix_align_environment(latex_code: str) -> str:
    return (
        latex_code
        .replace(r'\begin{align}', r'\begin{aligned}')
        .replace(r'\end{align}', r'\end{aligned}')
    )


def fix_callout_formulas(text: str) -> str:
    # lines = text.split('\n')
    # processed_lines = []
    #
    # for line in lines:
    #     # 使用正则表达式匹配以 '>' 开头，后面跟着 '$$' 或 '```' 的行
    #     # \s* 允许 '>' 和 '$$' 之间有空格
    #     if re.match(r'^\s*>\s*(\$\$|```)', line):
    #         # 移除行首的 '>' 及相关空格
    #         processed_lines.append(re.sub(r'^\s*>\s*', '', line))
    #     else:
    #         processed_lines.append(line)
    #
    # return '\n'.join(processed_lines)
    # pattern = re.compile(r'^\s*>\s*(\$\$|```)', flags=re.MULTILINE)
    #
    # # 现在调用 sub() 时，不需要再传入 flags
    # # 替换字符串 r'\1' 会用第一个捕获组的内容（即 '$$' 或 '```'）
    # # 替换掉整个匹配项（例如 '> $$'）
    # return pattern.sub(r'\1', text)
    return preprocess_markdown_quotes(text)

def split_inline_display_math(tex: str) -> str:
    tex = unescape_dollars(tex)
    # $$ 后有文字：变成 "$$\n内容"
    tex = re.sub(r'\$\$\s*([^\s\n].*?)', r'$$\n\1', tex)
    # $$ 前有文字：变成 "内容\n$$"
    tex = re.sub(r'([^\n]+?)\s*\$\$', r'\1\n$$', tex)
    return tex

def replace_tagged_dollars(tex: str) -> str:
    """
    终极修复版：
    1. 检测所有 $$...$$ 块。
    2. 如果块内包含 \\tag，则触发转换。
    3. 转换逻辑能处理 \tag{...} 和 \tag... 两种形式。
    4. 对不含 \\tag 的块，保持原样不动。
    """

    def ultimate_replacer(match):
        original_block = match.group(0)
        content = match.group(1)

        # 1. 检测阶段：简单、鲁棒地检查是否存在 "\tag"
        if r'\tag' not in content:
            # 不存在 \tag，原样返回，确保不破坏任何东西
            return original_block

        # --- 如果代码执行到这里，说明 \tag 确实存在 ---

        # 2. 提取阶段：使用一个更强大的正则来提取标签内容
        #    这个正则可以匹配 \tag{content} 或 \tag content
        #    - \\tag\s* : 匹配 "\tag" 和后面的空格
        #    - (?:\{(.*?)\}|([^\s{]+)) : 这是一个非捕获组 (?:...)
        #      - \{.*?\} : 匹配花括号内的所有内容
        #      - | : 或
        #      - [^\s{]+ : 匹配一个或多个不是空格也不是左花括号的字符
        tag_extractor_pattern = r'\\tag\s*(?:\{(.*?)\}|([^\s{]+))'
        tag_match = re.search(tag_extractor_pattern, content)

        tag_content = ""
        content_without_tag = content

        if tag_match:
            # tag_match.group(1) 对应 \{.*?\} 的捕获
            # tag_match.group(2) 对应 [^\s{]+ 的捕获
            # 两者中只有一个会有内容
            tag_content = tag_match.group(1) if tag_match.group(1) is not None else tag_match.group(2)

            # 从原始内容中移除整个 \tag... 部分
            # 使用 re.sub 比字符串替换更安全
            content_without_tag = re.sub(tag_extractor_pattern, '', content, count=1).strip()
        else:
            # 这是一个安全回退，理论上不应该被触发
            # 如果发生了，意味着 \tag 后面跟了一些我们没预料到的奇怪结构
            # 此时，我们选择不转换，打印一个警告，并返回原始块以避免崩溃
            print(f"WARNING: Found '\\tag' but couldn't parse it in block:\n{original_block}")
            return original_block

        # 3. 替换阶段：构建正确的 equation 环境
        return f"\\begin{{equation}}\n{content_without_tag}\n\\tag{{{tag_content}}}\n\\end{{equation}}"

    # 外层正则表达式保持不变
    return re.sub(r'\$\$(.*?)\$\$', ultimate_replacer, tex, flags=re.DOTALL)

def unescape_dollars(tex: str) -> str:
    # 将所有 \$\$ 替换成 $$
    return tex.replace(r'\$\$', '$$')

def unquote_latex_blocks(lines: list[str]) -> list[str]:
    output = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # 匹配 > $$ 起始
        if re.match(r'^\s*>\s*\$\$\s*$', line):
            # ✅ 找到起始 quote-math-block
            block = []
            block.append('$$')  # 去掉 >

            i += 1
            while i < len(lines):
                current = lines[i]
                if re.match(r'^\s*>\s*\$\$\s*$', current):  # 终止符
                    block.append('$$')
                    i += 1
                    break
                elif re.match(r'^\s*>\s?(.*)', current):  # 去掉 > 前缀
                    block.append(re.sub(r'^\s*>\s?', '', current))
                else:
                    # 非 > 开头：说明结构坏了，保守退出
                    break
                i += 1

            output.extend(block)
        else:
            output.append(line)
            i += 1
    return output

def preprocess_markdown_quotes(text: str) -> str:
    lines = text.splitlines()
    processed = unquote_latex_blocks(lines)
    return '\n'.join(processed).replace(r'Alternative Proof', 'Alternative-Proof')

def fix_mathbb_k(tex: str) -> str:
    # 匹配 $...$ 或 $$...$$ 中的 \mathbb k
    return re.sub(r'\\mathbb\s*k\b', r'\\Bbbk', tex)

def fix_smaller_than(tex: str) -> str:
    tex = re.sub(r'\\<', '<',tex)
    tex = re.sub(r'\\>', '>',tex)
    return tex

def extract_banner_path(markdown_text: str) -> tuple[str, str | None]:
    import re
    # 识别 Obsidian YAML 区块
    match = re.match(r"^---\n(.*?)\n---\n", markdown_text, re.DOTALL)
    if not match:
        return markdown_text, None

    yaml_block = match.group(1)
    rest_text = markdown_text[match.end():]

    banner_match = re.search(r"banner:\s*['\"]?\[\[(.*?)\]\]['\"]?", yaml_block)
    if banner_match:
        banner_path = banner_match.group(1)
        return rest_text, banner_path
    else:
        return markdown_text, None

from functools import partial
def _array_replacer(match: re.Match, target_env: str) -> str:
    """
    这是一个 re.sub 的 "替换函数". 它接收一个匹配对象并决定如何行动。

    匹配组 (match.group) 的结构:
    - group(1): 左括号, e.g., r'\\left('
    - group(2): 完整的列描述符, e.g., r'{ccc|c}' or r'{}', or None if not present
    - group(3): 数组内容
    - group(4): 右括号, e.g., r'\\right)'
    """
    column_spec = match.group(2)

    # --- 这是您建议的核心判断逻辑 ---
    # 检查列描述符是否存在且非空
    if column_spec:
        # 如果存在，剥离花括号和空格，检查里面是否还有内容
        # 例如 "{ ccc }" -> "ccc"
        inner_spec = column_spec.strip()[1:-1].strip()
        if inner_spec:
            # 描述符非空 (e.g., {c}, {c|c}), 不进行替换，返回原始匹配的完整字符串
            return match.group(0)

    # --- 如果通过了判断 (描述符为空或不存在), 则执行替换 ---
    left_delimiter = match.group(1)
    content = match.group(3)
    right_delimiter = match.group(4)

    # 如果没有括号 (裸数组), 我们使用 'matrix' 作为默认环境
    if not left_delimiter and not right_delimiter:
        target_env = 'matrix'

    return f"\\begin{{{target_env}}}{content}\\end{{{target_env}}}"


def replace_array_with_matrix_environments(latex: str) -> str:
    """
    智能地将 array 环境转换为 matrix 环境。
    - 使用简单的正则表达式进行查找。
    - 使用清晰的 Python if/else 逻辑进行判断和替换。
    - 只替换那些列描述符为空或不存在的 array 环境。
    """

    # 定义匹配规则：一个左括号，一个 array，一个右括号
    # 括号部分使用非捕获组 (?:...)
    left_delim_pattern = r"(\\left\s*(?:\(|\[|\\vert|\\Vert|\||\\\|))"
    right_delim_pattern = r"(\\right\s*(?:\)|\]|\\vert|\\Vert|\||\\\|))"

    # array 核心模式: \begin{array} 后面跟着一个可选的 {...} 列描述符
    array_pattern = r"\\begin\{array\}"
    # (\s*\{[^}]*\})?  <-- 捕获组(2): 可选的列描述符. 这是判断的关键!
    column_spec_pattern = r"(\s*\{[^}]*\})?"

    # 内容和结尾
    content_pattern = r"(.*?)"  # 捕获组(3): 内容
    end_pattern = r"\\end\{array\}"

    # --- STAGE 1: 处理带括号的数组 ---
    # 我们将分步处理不同类型的括号，以决定目标环境 (pmatrix, bmatrix, etc.)
    rules = [
        {'name': 'pmatrix', 'left': r"\\left\s*\(", 'right': r"\\right\s*\)"},
        {'name': 'bmatrix', 'left': r"\\left\s*\[", 'right': r"\\right\s*\]"},
        # 将 | 和 \vert 合并处理
        {'name': 'vmatrix', 'left': r"\\left\s*(?:\\vert|\|)", 'right': r"\\right\s*(?:\\vert|\|)"},
        # 将 || 和 \Vert 合并处理
        {'name': 'Vmatrix', 'left': r"\\left\s*(?:\\Vert|\\\|)", 'right': r"\\right\s*(?:\\Vert|\\\|)"}
    ]

    for rule in rules:
        # 为每种括号构建完整的匹配模式
        full_pattern = re.compile(
            f"({rule['left']})"  # Group 1: 左括号
            f"{array_pattern}"
            f"{column_spec_pattern}"  # Group 2: 列描述符
            f"{content_pattern}"  # Group 3: 内容
            f"{end_pattern}"
            f"({rule['right']})",  # Group 4: 右括号
            flags=re.DOTALL
        )

        # 使用 partial 将目标环境名传递给替换函数
        replacer_func = partial(_array_replacer, target_env=rule['name'])
        latex = full_pattern.sub(replacer_func, latex)

    # --- STAGE 2: 处理所有剩下符合条件的 "裸" 数组 (没有 \left \right) ---
    naked_pattern = re.compile(
        # 用 () 表示空的左右括号，这样可以复用 _array_replacer 函数
        r"()?"  # Group 1: 左括号 (空)
        f"{array_pattern}"
        f"{column_spec_pattern}"  # Group 2: 列描述符
        f"{content_pattern}"  # Group 3: 内容
        f"{end_pattern}"
        r"()?",  # Group 4: 右括号 (空)
        flags=re.DOTALL
    )
    # 对于裸数组，默认目标是 'matrix'，这会在 _array_replacer 内部处理
    naked_replacer_func = partial(_array_replacer, target_env='matrix')
    latex = naked_pattern.sub(naked_replacer_func, latex)

    return latex

def preprocess_nested_blockquotes(markdown_text: str) -> str:
    """
    预处理Markdown文本，以规避texmath插件在特定嵌套块引用中的bug。

    它会查找所有以 ">>" 开头的行，如果该行不是一个嵌套的callout
    (即，不是以 ">>[!" 开头)，则会移除行首的一个 ">" 字符。
    这能有效地将一个非callout的嵌套块引用“降级”为一级块引用，
    从而避免触发渲染器的死循环。

    Args:
        markdown_text: 原始的Markdown文件内容。

    Returns:
        经过预处理的Markdown文件内容。
    """
    lines = markdown_text.split('\n')
    processed_lines = []

    for line in lines:
        # 核心逻辑：
        # 1. 行是否以 ">>" 开头？
        # 2. 如果是，它是否 *不是* 一个嵌套的 callout (">>X" 不是 ">>[!")？
        #    我们检查剥离了前缀'>>'和可选空格后的剩余部分是否以 '[!' 开头。

        stripped_line = line.lstrip()  # 处理行首的空格，增加鲁棒性

        if stripped_line.startswith('>>'):
            # 检查它是否是一个 callout
            # ">> [!note]" -> lstrip(' >') -> "[!note]"
            content_after_quotes = stripped_line.lstrip(' >')
            if not content_after_quotes.startswith('[!'):
                # 这就是我们要处理的目标行！
                # 找到第一个非空格字符的位置，然后移除它前面的一个'>'
                first_char_index = len(line) - len(stripped_line)
                quote_index = line.find('>', first_char_index)
                if quote_index != -1:
                    processed_lines.append(line[:quote_index] + line[quote_index + 1:])
                else:  # 理论上不会发生，但作为安全措施
                    processed_lines.append(line)
            else:
                # 这是一个嵌套的callout，我们不动它
                processed_lines.append(line)
        else:
            # 这不是一个嵌套的块引用，我们不动它
            processed_lines.append(line)

    return '\n'.join(processed_lines)


def fix_kern_syntax(latex: str) -> str:
    # 列出常见的需要修复的尺寸命令
    # 注意：这些命令在原生 TeX 中期望后面直接跟数值，不带花括号。
    dimension_commands = [
        "kern",
        "raise",
        "moveleft",
        "moveright"
    ]

    pattern_core = "|".join(dimension_commands)
    # The pattern looks for cmd followed by braces, e.g., \\raise{.4pt}
    # 1 will capture the command name (e.g., "raise")
    # 2 will capture the content inside the braces (e.g., ".4pt")
    pattern = r'\\(' + pattern_core + r')\s*\{([^}]+)\}'

    # The replacement uses the captured groups to form the correct syntax: cmd content
    replacement = r'\\\1 \2'

    return fix_dimension_spacing_syntax(re.sub(pattern, replacement, latex))

def fix_dimension_spacing_syntax(latex: str) -> str:
    """
    修复 TeX 尺寸单位前出现多余空格的问题。
    将 "1 em" 这样的写法修正为 "1em"。
    """
    # TeX 中常见的长度单位
    units = [
        "pt", "pc", "in", "bp", "cm", "mm",
        "dd", "cc", "sp", "em", "ex", "mu"
        # "rem", "vh", "vw" 等是 CSS 单位，在 LaTeX 中不常用，
        # 但如果你的笔记中有，也可以加上
    ]

    # 构建正则表达式
    # (\d*\.?\d+)  : 匹配数字 (整数或小数)
    # \s+          : 匹配一个或多个空格
    # (em|pt|...)  : 匹配我们定义的单位之一
    # 我们用 (?i) 来忽略大小写，尽管 TeX 单位通常是小写的
    pattern_core = "|".join(units)
    pattern = re.compile(r'(\d*\.?\d+)\s+(' + pattern_core + r')', re.IGNORECASE)

    # 替换模式：将 "数字 空格 单位" 替换为 "数字单位"
    # \1 代表数字部分，\2 代表单位部分
    replacement = r'\1\2'

    return pattern.sub(replacement, latex)


def replace_custom_arrow_tricks(latex: str) -> str:
    """
    查找并替换已知的、用于生成特殊符号的 "hack" 或 "trick" 写法。
    这比尝试修复其内部的复杂语法要健壮得多。
    """
    # 定义一个 (查找, 替换) 的规则字典，方便未来扩展
    # 注意：使用 raw string (r"...") 来避免反斜杠的转义问题
    tricks_map = {
        r"\longleftarrow{\raise{.4pt}{\hspace{-5pt}\shortmid}}": r"\longmapsfrom ",
        # 未来可以添加更多规则，比如右箭头的 trick
        # r"\longrightarrow{...trick...}": r"\longmapsto",
    }

    for find_str, replace_str in tricks_map.items():
        latex = latex.replace(find_str, replace_str)

    return latex

def replace_bbox(latex: str) -> str:
    pattern = re.compile(r'\\bbox(?:\[[^\]]*\])?{([^}]*)}')
    return pattern.sub(r'\\boxed{\1}', latex)

def fix_choose(latex: str) -> str:
    return re.sub(r'(\w+)\s*\\choose\s*(\w+)', r'\\binom{\1}{\2}', latex)

def fix_tcolorbox_label_tcolorbox(content: str) -> str:
    """
    Iteratively corrects misplaced \\label commands between nested, breakable tcolorboxes.
    A single misplaced label in an N-level nested structure requires N-1 passes to "bubble out".
    The loop continues until no more substitutions can be made.
    """
    # The pattern remains the same
    pattern = re.compile(
        r"(\\end\{tcolorbox\})\s*(\\label\{[^\}]+\})\s*(\\end\{tcolorbox\})",
        re.MULTILINE
    )
    # The replacement logic also remains the same
    replacement = r"\1\n\3\n\2"

    # --- Iterative Application ---
    # We use a while True loop that breaks when a pass makes no changes.
    while True:
        # re.subn is perfect here: it returns the new string and the number of substitutions made.
        new_content, num_subs = pattern.subn(replacement, content)

        # If no substitutions were made in this pass, the work is done.
        if num_subs == 0:
            break

        # Otherwise, update the content and loop again for the next level.
        content = new_content

    return content

_BAD_PTR_LINE = re.compile(
    r'^[ \t]*\\\^\{\}.*?(?:\r?\n|\r|\Z)',
    re.MULTILINE,
)

def remove_bad_tex_block_pointers(text: str) -> str:
    return _BAD_PTR_LINE.sub('', text)


def get_shared_latex_preamble() -> str:
    """
    Returns the shared LaTeX preamble content for all document types.
    This ensures visual and functional consistency.
    It does NOT include \\documentclass or geometry settings, as those are
    class-specific.
    """
    return r"""
\usepackage{fontspec}       % Unicode 字体支持
\usepackage{xeCJK}          % 中文支持

\setmainfont{Latin Modern Roman}
\setsansfont{Latin Modern Sans}
\setmonofont{Latin Modern Mono}

% 设置主字体 (正文)
\setCJKmainfont[ItalicFont = FandolKai]{FandolSong}

% 设置无衬线字体 (用于 \sffamily 或某些标题)
% FandolHei 同样自带粗体版本，fontspec 会自动处理。
\setCJKsansfont{FandolHei}

% 设置等宽字体 (用于代码块 \texttt{})
\setCJKmonofont{FandolFang}

\usepackage{amsmath}
\usepackage{amssymb}

\usepackage{gensymb}
\usepackage{mathrsfs}
\usepackage{extpfeil}
\usepackage{graphicx}
\usepackage{grffile}        % 支持带点的文件名
\usepackage{svg}
\usepackage[colorlinks=true, urlcolor=green, linkcolor=blue, citecolor=blue]{hyperref}
\usepackage[most]{tcolorbox} % 使用 [most] 以获得更多功能
\usepackage{upquote}
\usepackage{xcolor}
\usepackage{soul}
\usepackage{booktabs}       % For \toprule, \midrule, \bottomrule
\usepackage{tabularx}       % For auto-wrapping tables

\usepackage{everypage}  % <-- 1. 引入 everypage 包
\usepackage{lastpage}   % <-- 2. 引入 lastpage 包，用于获取总页数
\usepackage{refcount}

\usepackage{titling}        % 用于自定义标题格式
\pretitle{\begin{center}\Huge\bfseries}
\posttitle{\end{center}}

\definecolor{yellow}{HTML}{FFFF00}
\sethlcolor{yellow}

\newtcolorbox{calloutbox}[2][]{
    colback={#2!10!white},
    colframe={#2!75!black},
    coltext=black,
    fonttitle=\bfseries,
    title={#1},
    arc=2mm,
    boxrule=1pt,
    breakable,
}

\newcommand{\myhl}[1]{\colorbox{yellow}{#1}}
\let\hl\myhl

\newcommand{\longmapsfrom}{\mathrel{\longleftarrow\mkern-12mu\mid}}

\setcounter{MaxMatrixCols}{30}
"""

def extract_relevant_latex_error(log: str) -> str:
    """
    从完整的 XeLaTeX 日志中提取出核心的错误信息。
    它会找到第一个以 '!' 开头的行，并返回那一部分的上下文。
    """
    lines = log.splitlines()
    error_start_index = -1

    # 找到第一个错误标志 '!' 所在的行
    for i, line in enumerate(lines):
        if line.strip().startswith('!'):
            error_start_index = i
            break

    if error_start_index != -1:
        # 我们找到了错误！
        # 为了提供上下文，我们从错误行往前取几行，往后取几行
        context_before = 2
        context_after = 8

        start = max(0, error_start_index - context_before)
        end = min(len(lines), error_start_index + context_after)

        relevant_lines = lines[start:end]
        return "\n".join(relevant_lines)
    else:
        # 如果没有找到 '!'，说明可能是其他类型的错误（比如文件没找到）
        # 在这种情况下，返回日志的最后一部分通常比较有用
        last_lines = lines[-15:]
        return "Could not find a standard LaTeX error ('!'). Showing last 15 lines of log:\n" + "\n".join(last_lines)

# Registry of processors. To avoid clumsy recursive call chains in renderer.py
BUILTIN_POST_PROCESSORS = {
    # Key 是不带 '$' 的名字，Value 是函数对象
    "fix_tcolorbox_label_tcolorbox": fix_tcolorbox_label_tcolorbox,
    "fix_choose": fix_choose,
    "replace_bbox": replace_bbox,
    "replace_array_with_matrix_environments": replace_array_with_matrix_environments,
    "fix_kern_syntax": fix_kern_syntax,
    "fix_smaller_than": fix_smaller_than,
    "fix_mathbb_k": fix_mathbb_k,
    "replace_tagged_dollars": replace_tagged_dollars,
    "split_inline_display_math": split_inline_display_math,
    "replace_custom_arrow_tricks": replace_custom_arrow_tricks,
    "fix_align_environment": fix_align_environment,
    "remove_bad_tex_block_pointers": remove_bad_tex_block_pointers,
    # 如果有其他函数也需要加入，就加在这里
}
BUILTIN_PRE_PROCESSORS = {
    "normalize_unicode": normalize_unicode,
    "insert_blank_blockquote_lines": insert_blank_blockquote_lines,
    "fix_callout_formulas": fix_callout_formulas,
    "preprocess_nested_blockquotes": preprocess_nested_blockquotes,
}
