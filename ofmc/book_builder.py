import subprocess
from pathlib import Path
from typing import Callable

from .utils import get_shared_latex_preamble, extract_relevant_latex_error
from .config import Config

import re
from alive_progress import alive_bar
from tqdm import tqdm

def build_book(cfg: Config, compiled_tex_files: dict, sorter_func: Callable):
    """
    Generates a master TeX file and compiles it into a final book PDF.

    Args:
        cfg: The application configuration object.
        compiled_tex_files: A dictionary mapping source .md Path to output .tex Path.
    """
    print("📖 Starting book compilation...")

    master_tex_content = generate_master_tex(cfg, compiled_tex_files, sorter_func)

    master_tex_path = cfg.output_dir / "_master_book.tex"
    final_pdf_name = Path(cfg.book_title.replace(" ", "_")).with_suffix('.pdf').name
    final_pdf_path = cfg.output_dir / final_pdf_name

    with open(master_tex_path, "w", encoding="utf-8") as f:
        f.write(master_tex_content)

    print(f"Master TeX file created at: {master_tex_path}")
    print("Running XeLaTeX to build the book (this may take a while)...")

    # LaTeX 需要多次编译以生成目录和交叉引用
    # =========================================================================
    #  核心改动：使用新的带进度条的编译函数
    # =========================================================================
    total_passes = 3
    for i in range(total_passes):
        # 调用我们的新函数
        success, log_output = _run_latex_pass_with_progress(
            tex_file=master_tex_path,
            output_dir=cfg.output_dir,
            pass_num=i + 1,
            total_passes=total_passes
        )

        if not success:
            print(f"\n❌ XeLaTeX compilation failed on pass {i + 1}.")
            print("--- Relevant XeLaTeX Log ---")
            # 假设您有一个 extract_relevant_latex_error 函数
            print(extract_relevant_latex_error(log_output))
            print(f"Full log can be found in: {master_tex_path.with_suffix('.log')}")
            return  # 编译失败，提前退出

    # =========================================================================


    # 重命名最终的 PDF
    source_pdf = master_tex_path.with_suffix('.pdf')
    if source_pdf.exists():
        source_pdf.rename(final_pdf_path)
        print(f"✅ Book successfully compiled: {final_pdf_path}")
    else:
        print("❌ Final PDF not found after compilation.")

def generate_master_tex(cfg: Config, compiled_tex_files: dict, sorter_func: Callable) -> str:
    """Generates the content for the master TeX file."""

    if cfg.cover_image:
        if cfg.cover_image.exists():
            cover_image = str(cfg.cover_image.resolve())
            print(f"✅ Found cover image: {cover_image}")
        else:
            cover_image = None
            print(f"⚠️ Specified cover image not found.")

    titlepage = ""
    if cover_image:
        titlepage = f"""
        
\\begin{{titlepage}}
    \\centering
    \\vspace*{{\\stretch{{1}}}}
    
    {{\\Huge\\bfseries {cfg.book_title}\\par}}
    \\vspace{{1.5cm}}
    {{\\Large {cfg.author}\\par}}
    \\vspace{{2cm}}
    {{\\large \\today\\par}}
    \\vspace{{2cm}} % 图片和标题之间的一些间距

    \\begin{{center}}
        \\includegraphics[width=0.4\\textwidth]{{{cover_image}}}
    \\end{{center}}

    \\vspace*{{\\stretch{{2}}}}
\\end{{titlepage}}

"""

    # --- Preamble ---
    tex = [
        # 1. 使用 book 文档类。'twoside' 是书籍印刷的标准，为左右页设置不同页边距。
        r"\documentclass[a4paper, 11pt, twoside]{book}",

        # 2. 插入完全一致的共享导言区！
        get_shared_latex_preamble(),

        # 3. 为 book 类设置页面几何。书籍的内外边距通常不同。
        r"\usepackage[a4paper, top=1in, bottom=1in, inner=0.9in, outer=1.1in]{geometry}",

        # 4. 文档元数据
        f"\\title{{{cfg.book_title}}}",
        f"\\author{{{cfg.author}}}",
        "\\date{\\today}",

        "\\AddEverypageHook{\\immediate\\write16{PYTEX-PROGRESS-SIGNAL \\thepage\\space of \\getpagerefnumber{LastPage}}}%",
        "",

        # 5. 文档主体开始
        "\\begin{document}",
        f"{titlepage}",
        "\\frontmatter", # <-- book类特有，用于生成罗马数字页码的前言部分
        "\\maketitle",
        "\\tableofcontents",
    ]

    # --- Front Matter ---
    if cfg.front_matter:
        tex.append("% --- Front Matter ---")
        for md_path_str in cfg.front_matter:
            md_path = cfg.vault_root / md_path_str
            tex_path = compiled_tex_files.get(md_path)
            if tex_path:
                # \include 需要相对于 master.tex 的路径，我们让它们都在 output_dir
                tex.append(f"\\include{{tex_chapters/{tex_path.name}}}")
            else:
                print(f"⚠️  Warning: Front matter file not found in compiled files: {md_path_str}")

    # --- Main Matter (Table of Contents, Parts, Chapters) ---
    tex.append("\\mainmatter")

    # 解析 book_parts
    for part_item in cfg.book_parts:
        if isinstance(part_item, str):
            part_dir, part_title = part_item, Path(part_item).name
        else:  # 是 [path, title] 格式
            part_dir, part_title = part_item

        tex.append(f"\\part{{{part_title}}}")

        # 找到这个 part 目录下的所有 md 文件并排序
        part_full_path = cfg.vault_root / part_dir
        if part_full_path.is_dir():
            if sorter_func:
                print(f"✅ Using custom sorting method from: {cfg.sorting_script.name}")
            else:
                print("ℹ️ Using default alphabetical sorting for chapters.")

            md_files_in_part = list(part_full_path.glob("*.md"))

            # 步骤 2: 根据 sorter_func 是否存在，应用不同的排序策略
            if sorter_func:
                # 如果自定义排序函数存在，就用它作为排序的 `key`
                # .sort() 方法会就地修改列表
                md_files_in_part.sort(key=sorter_func)
            else:
                # 如果不存在，就回退到默认的按字母排序
                md_files_in_part.sort()

            for md_path in md_files_in_part:
                tex_path = compiled_tex_files.get(md_path)
                if tex_path:
                    tex.append(f"\\include{{tex_chapters/{tex_path.name}}}")
                #else:
                    #print(f"⚠️  Warning: Chapter file not found in compiled files: {md_path}")

        else:
            print(f"⚠️  Warning: Part directory not found: {part_full_path}")

    # --- Back Matter ---
    if cfg.back_matter:
        tex.append("\\backmatter")
        tex.append("% --- Back Matter ---")
        for md_path_str in cfg.back_matter:
            md_path = cfg.vault_root / md_path_str
            tex_path = compiled_tex_files.get(md_path)
            if tex_path:
                tex.append(f"\\include{{tex_chapters/{tex_path.name}}}")
            else:
                print(f"⚠️  Warning: Back matter file not found in compiled files: {md_path_str}")

    tex.append("\\end{document}")
    return "\n".join(tex)


PROGRESS_RE = re.compile(r"PYTEX-PROGRESS-SIGNAL\s+(\d+)(?:\s+of\s+(\d+))?")


def _run_latex_pass_with_progress(
        tex_file: Path,
        output_dir: Path,
        pass_num: int,
        total_passes: int
) -> tuple[bool, str]:
    command = ["xelatex", "-interaction=nonstopmode", "-shell-escape", tex_file.name]

    process = subprocess.Popen(
        command,
        cwd=output_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='ignore'
    )

    full_log = []

    # --- 阶段 1: 侦察 ---
    first_page = None
    total_pages = None
    for line in iter(process.stdout.readline, ''):
        full_log.append(line)
        match = PROGRESS_RE.search(line)
        if match:
            first_page = int(match.group(1))
            if match.group(2):
                total_pages = int(match.group(2))
            break

    if first_page is None:
        print(f"\n[Warning] Pass {pass_num}: No progress signals received. Maybe a quick pass or an error.")
        process.stdout.close()
        return_code = process.wait()
        return return_code == 0, "".join(full_log)

    # --- 阶段 2: 执行 ---
    bar_style = "smooth" if total_pages else "classic"

    with alive_bar(
            total=total_pages,
            title=f"  Pass {pass_num}/{total_passes}",
            spinner="waves2",
            length=40,
            bar=bar_style
    ) as bar:

        last_known_page = 0

        # --- 核心逻辑: 增量更新 ---
        def update_progress(page):
            nonlocal last_known_page
            # 确保页码是前进的，防止意外情况
            if page > last_known_page:
                increment = page - last_known_page
                bar(increment)
                last_known_page = page

        # 手动处理第一个信号
        bar.text(f"Page {first_page} of {total_pages or '...'}")
        update_progress(first_page)

        # 处理剩余的输出流
        for line in iter(process.stdout.readline, ''):
            full_log.append(line)
            match = PROGRESS_RE.search(line)
            if match:
                current_page = int(match.group(1))
                bar.text(f"Page {current_page} of {total_pages or '...'}")
                update_progress(current_page)

    process.stdout.close()
    return_code = process.wait()

    return return_code == 0, "".join(full_log)