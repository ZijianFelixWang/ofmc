# ofmc/batch_compiler.py
import importlib
import os
import sys
import shutil
import uuid
import subprocess
import time
from pathlib import Path
from typing import Callable

import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed

from pypdf import PdfWriter
from tqdm import tqdm

from .parser import OFMCompiler  # 导入您的核心编译器

import colorama
from colorama import Fore, Style

from .book_builder import build_book
from .utils import extract_relevant_latex_error

import re


# +++ 新增：全局扫描与注册函数 +++
def scan_and_build_registry(files_to_compile: list[Path], vault_root: Path) -> dict:
    """
    [阶段一] 扫描所有文件，构建链接目标注册表。
    """
    print(f"{Fore.CYAN}🔎 Pass 1/3: Scanning {len(files_to_compile)} files for link targets...{Style.RESET_ALL}")

    registry = {}
    heading_re = re.compile(r"^\s*#+\s+(.+?)\s*$")
    # 匹配行尾的 ^xxxxxx，但也会匹配独立一行的
    block_id_re = re.compile(r'\^([a-fA-F0-9]{6})\s*$')

    def create_latex_label(target_key: str) -> str:
        """为给定的目标字符串创建一个唯一的、对 LaTeX 安全的标签。"""
        safe_str = re.sub(r'[^a-zA-Z0-9]', '', target_key)
        # 使用 uuid 的一小部分确保唯一性，防止不同文件的相同标题冲突
        unique_hash = str(uuid.uuid5(uuid.NAMESPACE_DNS, target_key))[:8]
        return f"wikilink:{safe_str[:40]}:{unique_hash}"

    for md_path in tqdm(files_to_compile, desc="Scanning", unit="file"):
        note_name = md_path.stem

        # 1. 注册文件名本身
        registry[note_name] = create_latex_label(note_name)

        try:
            content = md_path.read_text(encoding='utf-8')
            for line in content.splitlines():
                # 2. 注册标题
                h_match = heading_re.match(line)
                if h_match:
                    heading_text = h_match.group(1).strip()
                    target_key = f"{note_name}#{heading_text}"
                    registry[target_key] = create_latex_label(target_key)

                # 3. 注册块ID
                b_match = block_id_re.search(line)
                if b_match:
                    block_id = b_match.group(1)
                    target_key = f"{note_name}^{block_id}"
                    registry[target_key] = create_latex_label(target_key)
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not read or parse {md_path.name} during scan: {e}{Style.RESET_ALL}")

    print(f"{Fore.GREEN}✅ Found and registered {len(registry)} unique link targets.{Style.RESET_ALL}")
    return registry

def logger_thread_worker(log_queue: multiprocessing.Queue, pbar: tqdm):
    """
    这个函数在一个独立的线程中运行。
    它的唯一工作就是从共享队列中获取日志消息，
    并使用 pbar.write() 安全地打印它们。
    """
    while True:
        message = log_queue.get()
        if message is None:  # "None" 是我们约定的停止信号
            break
        pbar.write(str(message))

def find_markdown_files(root_dir: Path, excluded_patterns: list[str]) -> list[Path]:
    """
    使用 glob 模式查找所有 Markdown 文件，并排除匹配指定模式的路径。
    这支持类似 .gitignore 的模式匹配。

    Args:
        root_dir: Vault 的根目录。
        excluded_patterns: 一个包含 glob 模式的字符串列表，用于排除文件或目录。
                           例如: ["*.excalidraw.md", "Templates/*", "ignored_folder"]

    Returns:
        一个经过排序和过滤的 Path 对象列表。
    """

    # =================================================================
    #  ROBUSTNESS CHECK: 验证输入数据的类型
    # =================================================================

    if not isinstance(excluded_patterns, list):
        raise TypeError(
            f"Configuration Error: 'excluded' must be a list of strings, but got {type(excluded_patterns).__name__}")

    for i, pattern in enumerate(excluded_patterns):
        if not isinstance(pattern, str):
            # 抛出一个非常明确的错误，告诉用户哪里错了
            raise TypeError(
                f"Configuration Error in 'excluded' list at position {i}: \n"
                f"Expected a string pattern, but found a {type(pattern).__name__}: {pattern!r}.\n"
                f"Please ensure all items in the 'excluded' list are simple strings (e.g., \"Templates/*\")."
            )
    # =================================================================

    # 1. 使用 rglob 高效地递归查找所有 .md 文件。
    #    使用 sorted() 保证结果的顺序稳定性。
    all_md_files = sorted(root_dir.rglob("*.md"))

    # 如果没有排除规则，直接返回所有文件
    if not excluded_patterns:
        return all_md_files

    filtered_files = []
    for file_path in all_md_files:
        # 2. 获取文件相对于 vault 根目录的路径，用于匹配。
        relative_path = file_path.relative_to(root_dir)

        # 3. 检查文件路径是否与任何排除模式匹配。
        #    我们不仅检查文件本身，还检查它的所有父目录。
        #    这允许像 "Templates" 这样的模式排除整个目录。
        parts_to_check = [relative_path] + list(relative_path.parents)

        is_excluded = any(
            part.match(pattern)
            for pattern in excluded_patterns
            for part in parts_to_check
        )

        if not is_excluded:
            filtered_files.append(file_path)

    return filtered_files

def get_temp_dir() -> Path:
    """
    优先使用/dev/shm，否则回退到家目录的.cache。返回 Path 对象。
    """
    shm_path = Path('/dev/shm')
    if shm_path.exists():
        temp_root = shm_path
    else:
        temp_root = Path.home() / '.cache'

    ofmc_temp_dir = temp_root / 'ofmc_runs' / str(uuid.uuid4())
    ofmc_temp_dir.mkdir(parents=True, exist_ok=True)
    return ofmc_temp_dir


def compile_single_file_worker(md_path: Path,
                               config,
                               temp_dir: Path,
                               log_queue: multiprocessing.Queue,
                               # --- 新增参数 ---
                               is_book_mode: bool,
                               output_target_dir: Path,
                               link_registry: dict,
                               build_assets_dir: Path,
                               max_name_length: int = 18,
                               post_processors: list = None,
                               pre_processors: list = None):
    """
    在并行进程中运行的单个文件编译工作函数。
    - 在图书模式下，它生成 .tex 章节文件并返回其路径。
    - 在独立模式下，它生成 .pdf 文件并返回其路径。
    """

    def worker_logger(message: any):  # 接受任何类型的消息
        """使用 colorama 库实现带颜色高亮的日志记录器。"""
        prefix = f"[{md_path.stem:<{max_name_length}}]"

        # =========================================================================
        #  FIX: Explicitly convert 'message' to a string before concatenation.
        #  This handles Path objects, exceptions, and other non-string types gracefully.
        # =========================================================================
        log_line = prefix + " " + str(message)

        if '✅' in log_line:
            formatted_log = f"{Fore.GREEN}{log_line}{Fore.RESET}"
        elif '❌' in log_line or '💥' in log_line:
            formatted_log = f"{Fore.RED}{log_line}{Fore.RESET}"
        else:
            formatted_log = log_line
        log_queue.put(formatted_log)

    try:
        # 在每个进程中创建独立的编译器实例，保证进程安全
        compiler = OFMCompiler(
            vault_root=str(config.vault_root),
            author=config.author,
            link_registry=link_registry if is_book_mode else None,
            build_assets_dir=build_assets_dir,
            post_processors=post_processors if post_processors else None,
            pre_processors=pre_processors if pre_processors else None,
        )

        # =========================================================================
        #  核心修改：根据模式选择不同的工作流
        # =========================================================================
        if is_book_mode:
            # --- 图书模式：生成 .tex 章节文件 ---
            worker_logger("📖 Generating TeX chapter...")

            # 告诉编译器生成 "chapter" 片段，而不是完整文档
            # **注意**: 这需要你的 OFMCompiler.compile 方法支持 mode 参数
            latex_content = compiler.compile(str(md_path), mode='chapter')

            # 输出路径是共享的、非临时的 TeX 目录
            final_tex_path = output_target_dir / md_path.with_suffix('.tex').name

            final_tex_path.write_text(latex_content, encoding='utf-8')
            worker_logger(f"✅ TeX chapter saved: {final_tex_path.name}")

            # 返回最终的 .tex 文件路径
            return md_path, final_tex_path

        else:
            # --- 独立文件模式：生成 .pdf 文件 (旧逻辑) ---
            worker_logger("📄 Compiling to standalone PDF...")

            # 告诉编译器生成完整的 "standalone" 文档
            latex_content = compiler.compile(str(md_path), mode='standalone')

            # 使用临时目录来处理中间文件
            # 文件名可以简单一些，因为目录本身是唯一的
            temp_tex_path = temp_dir / "document.tex"
            temp_pdf_path = temp_dir / "document.pdf"

            temp_tex_path.write_text(latex_content, encoding='utf-8')

            success = run_xelatex(temp_tex_path, temp_dir, logger=worker_logger)

            if success and temp_pdf_path.exists():
                # 返回在临时目录中的 pdf 路径
                return md_path, temp_pdf_path
            else:
                worker_logger(f"❌ PDF compilation failed for {md_path.name}")
                return md_path, None
        # =========================================================================

    except Exception as e:
        # 统一的错误处理，对两种模式都有效
        worker_logger(f"💥 CRITICAL ERROR Compiling {md_path.name}: {e}")
        import traceback
        worker_logger(traceback.format_exc())  # 打印详细的堆栈跟踪以帮助调试
        return md_path, None

def merge_pdfs(pdf_paths: list[Path], output_filename: Path):
    """将一系列PDF文件合并成一个大文件。"""
    merger = PdfWriter()
    print(f"\nMerging {len(pdf_paths)} PDFs into {output_filename}...")
    for pdf_path in tqdm(pdf_paths, desc="Merging", unit="file"):
        try:
            merger.append(str(pdf_path))
        except Exception as e:
            print(f"Warning: Could not append {pdf_path.name}. Reason: {e}")

    merger.write(str(output_filename))
    merger.close()
    print("Merge complete.")


# --- 这是本模块的主入口函数 ---
def run_batch_compilation(config):
    """批量编译的主调度函数，现在支持图书模式和独立文件模式。"""
    vault_root = config.vault_root
    output_dir = config.output_dir
    excluded = config.excluded

    files_to_compile = find_markdown_files(vault_root, excluded)
    if not files_to_compile:
        print("No markdown files to compile.")
        return

    print(f"Found {len(files_to_compile)} markdown files to process.")

    ### BOOK MODE CHANGE ###
    # 根据配置决定编译模式和最终目标
    is_book_mode = config.enable_book_compile
    link_registry = {}  # 初始化为空字典

    post_processors = config.post_processors
    pre_processors = config.pre_processors

    if is_book_mode:
        print("🚀 Book Compilation Mode Enabled.")

        # +++ 新增：在 book 模式下，执行扫描 +++
        link_registry = scan_and_build_registry(files_to_compile, vault_root)

        # --- 临时调试代码 ---
        import json
        debug_registry_path = output_dir / "debug_link_registry.json"
        with open(debug_registry_path, 'w', encoding='utf-8') as f:
            json.dump(link_registry, f, indent=2, ensure_ascii=False)
        print(f"📝 Debug: Link registry saved to {debug_registry_path}")
        # --- 结束临时代码 ---

        # 在图书模式下，我们先把所有 TeX 章节文件生成到一个地方
        # 这个目录将在最后被 book_builder 使用，所以它不是临时的
        tex_chapters_dir = output_dir / "tex_chapters"
        tex_chapters_dir.mkdir(parents=True, exist_ok=True)
        print(f"Intermediate TeX chapters will be saved to: {tex_chapters_dir}")
    else:
        print("📄 Individual PDF Compilation Mode.")
        individual_pdf_dir = output_dir / "individual_pdfs"
        individual_pdf_dir.mkdir(parents=True, exist_ok=True)
    ### END BOOK MODE CHANGE ###

    build_assets_dir = output_dir / "build_assets"
    os.makedirs(build_assets_dir, exist_ok=True)

    successful_compilations = []
    failed_compilations = []

    # 这个 map 现在可以存储 PDF 路径（独立模式）或 TeX 路径（图书模式）
    compiled_output_map = {}

    manager = multiprocessing.Manager()
    log_queue = manager.Queue()
    temp_dir_root = get_temp_dir()
    max_workers = max(1, os.cpu_count() - 2)
    max_name_length = max(len(p.stem) for p in files_to_compile) if files_to_compile else 0

    try:
        with tqdm(total=len(files_to_compile), desc="Processing", unit="file") as pbar:
            log_thread = threading.Thread(target=logger_thread_worker, args=(log_queue, pbar))
            log_thread.start()

            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for md_path in files_to_compile:
                    worker_temp_dir = temp_dir_root / str(uuid.uuid4())
                    worker_temp_dir.mkdir()

                    ### BOOK MODE CHANGE ###
                    # 决定 worker 的目标输出目录
                    # 图书模式下，worker 直接输出到共享的 tex_chapters_dir
                    # 独立模式下，worker 输出到它自己的临时目录
                    output_target_dir = tex_chapters_dir if is_book_mode else worker_temp_dir

                    # def compile_single_file_worker(md_path: Path,
                    #                                config,
                    #                                temp_dir: Path,
                    #                                log_queue: multiprocessing.Queue,
                    #                                # --- 新增参数 ---
                    #                                is_book_mode: bool,
                    #                                output_target_dir: Path,
                    #                                max_name_length: int = 18):

                    # 提交任务，传递新的参数来控制行为
                    future = executor.submit(
                        compile_single_file_worker,
                        md_path,
                        config,
                        worker_temp_dir,
                        log_queue,
                        is_book_mode,
                        output_target_dir,
                        link_registry,
                        build_assets_dir,
                        max_name_length,
                        post_processors,
                        pre_processors
                    )
                    ### END BOOK MODE CHANGE ###
                    futures[future] = md_path

                for future in as_completed(futures):
                    original_md_path = futures[future]
                    try:
                        # worker 现在返回 (源md路径, 最终输出路径)
                        # 输出路径是 .pdf (独立模式) 或 .tex (图书模式)
                        md_path, result_path = future.result()

                        if result_path:
                            compiled_output_map[md_path] = result_path
                            successful_compilations.append(md_path)
                        else:
                            failed_compilations.append(md_path)
                    except Exception as e:
                        failed_compilations.append(original_md_path)
                        log_queue.put(f"[run_batch_compilation] FATAL ERROR for {original_md_path.name}: {e}")

                    pbar.set_postfix_str(f"{original_md_path.stem}", refresh=True)
                    pbar.update(1)

            log_queue.put(None)
            log_thread.join()

        # --- 后处理步骤 ---
        print("\nAll files processed. Starting post-compilation tasks...")

        ### BOOK MODE CHANGE ###
        if is_book_mode:
            # 图书模式的后处理：调用 book_builder
            if successful_compilations:
                # compiled_output_map 包含 {md_path: tex_path} 的映射
                sorter_func = load_sorter_from_file(config.sorting_script)
                #print(sorter_func)
                build_book(config, compiled_output_map, sorter_func)
            else:
                print("No chapters were successfully compiled. Skipping book generation.")
        else:
            # 独立文件模式的后处理：复制和合并 PDF
            print("\nCopying compiled PDFs to output directory...")
            for md_path, src_pdf_path in tqdm(compiled_output_map.items(), desc="Copying", unit="file"):
                relative_path = md_path.relative_to(vault_root)
                output_pdf_path = (individual_pdf_dir / relative_path).with_suffix(".pdf")
                output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
                # 在独立模式下，src_pdf_path 是在临时目录里，需要 shutil.move 或 copy
                shutil.copy(src_pdf_path, output_pdf_path)

            if config.enable_simple_merge and compiled_output_map:
                # 注意：这里的 compiled_output_map 的值是临时文件路径，我们需要使用复制后的路径
                pdfs_to_merge = [
                    (individual_pdf_dir / p.relative_to(vault_root)).with_suffix(".pdf")
                    for p in successful_compilations
                ]
                vault_name = vault_root.name
                merged_pdf_path = output_dir / f"{vault_name} - Compiled Vault.pdf"
                print(f"\nMerging {len(pdfs_to_merge)} PDFs into a single file...")
                merge_pdfs(pdfs_to_merge, str(merged_pdf_path))
        ### END BOOK MODE CHANGE ###

    except KeyboardInterrupt:
        print("\n\n================================================================================")
        print(" 🛑 BATCH COMPILATION CANCELLED BY USER")
        print("================================================================================")
        print("Shutting down worker processes gracefully... Please wait.")
        # 当 `try` 块因为 KeyboardInterrupt 退出时，`with` 语句的 `__exit__`
        # 方法会被自动调用。它会调用 executor.shutdown(wait=True)，
        # 这会尝试等待已开始的任务完成，但不会开始新任务。
        # 这种行为已经足够“优雅”。我们只需捕获异常，打印消息，然后干净地退出。
        sys.exit(130) # 130 是脚本被 Ctrl+C 中断的标准退出码

    finally:
        # --- 7. 最终清理 ---
        print("Cleaning up temporary files...")
        shutil.rmtree(temp_dir_root, ignore_errors=True)

        # =================================================================
        #  MODIFICATION 3: 打印最终的总结报告
        # =================================================================
        print("\n" + "=" * 80)
        print(" BATCH COMPILATION SUMMARY")
        print("=" * 80)

        success_count = len(successful_compilations)
        failure_count = len(failed_compilations)

        print(f"Total files processed: {len(files_to_compile)}")
        print(f" ✅ Success: {success_count}")
        print(f" ❌ Failed:  {failure_count}")

        if failure_count > 0:
            success_rate = (success_count / (success_count + failure_count)) * 100
            print(f" 📊 Success Rate: {success_rate:.2f}%")

        if failed_compilations:
            print("\n--- Files that FAILED to compile ---")
            # 排序让输出更稳定、易于查看
            failed_compilations.sort()
            for md_path in failed_compilations:
                # 打印相对路径，更清晰
                print(f"  - {md_path.relative_to(vault_root)}")

        print("=" * 80)
        print("\nBatch compilation finished!")
        # =================================================================


def run_xelatex(
        tex_path: Path,
        working_dir: Path,
        logger: Callable = print,
        max_retries: int = 2,  # Initial attempt + 2 retries = 3 total
        retry_delay: float = 1.0  # Seconds to wait before retrying
):
    """
    Runs XeLaTeX with a two-pass approach and a robust retry mechanism.

    Args:
        tex_path: Path to the .tex file.
        working_dir: The directory where xelatex should run.
        logger: A logging function.
        max_retries: Number of times to retry after the first failure.
        retry_delay: Delay in seconds between retries.
    """
    command = [
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-shell-escape",
        tex_path.name
    ]

    total_attempts = max_retries + 1
    last_error_output = ""

    for attempt in range(1, total_attempts + 1):
        if attempt > 1:
            logger(f"⏳ Waiting {retry_delay}s before retrying... (Attempt {attempt}/{total_attempts})")
            time.sleep(retry_delay)

        logger(f"🚀 Starting compilation attempt {attempt}/{total_attempts} for {tex_path.name}")

        # --- Pass 1 ---
        logger(f"  - Running XeLaTeX pass 1/2...")
        result1 = subprocess.run(
            command, cwd=working_dir, capture_output=True, text=True, encoding='utf-8'
        )

        if result1.returncode != 0:
            logger(f"  - Pass 1 failed on attempt {attempt}.")
            last_error_output = result1.stdout
            continue  # Move to the next retry attempt

        # --- Proactive Delay to prevent race condition ---
        # Give the filesystem a moment to sync the .aux file before pass 2 reads it.
        time.sleep(0.1)

        # --- Pass 2 ---
        logger(f"  - Running XeLaTeX pass 2/2...")
        result2 = subprocess.run(
            command, cwd=working_dir, capture_output=True, text=True, encoding='utf-8'
        )

        if result2.returncode == 0:
            logger(f"✅ XeLaTeX compilation for {tex_path.name} completed successfully on attempt {attempt}.")
            return True  # Success!

        # If we are here, pass 2 failed
        logger(f"  - Pass 2 failed on attempt {attempt}.")
        last_error_output = result2.stdout
        # The loop will naturally continue to the next attempt

    # If the loop completes without returning True, all attempts have failed
    log_path = tex_path.with_suffix('.log')
    logger("\n" + "=" * 80)
    logger(f"❌ XeLaTeX FAILED PERMANENTLY for {tex_path.name} after {total_attempts} attempts.")
    logger(f"!!! See full log for details: {log_path}")
    logger("=" * 80)
    logger("\nRelevant output from last failed attempt:\n")
    logger(extract_relevant_latex_error(last_error_output))
    logger("\nEnd of XeLaTeX output")

    return False


def load_sorter_from_file(script_path: Path):
    """动态加载一个 Python 脚本并返回其 'get_sort_key' 函数。"""
    if not script_path or not script_path.is_file():
        return None

    try:
        spec = importlib.util.spec_from_file_location("custom_sorter", script_path)
        sorter_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sorter_module)

        if hasattr(sorter_module, "get_sort_key"):
            return getattr(sorter_module, "get_sort_key")
        else:
            print(f"⚠️  Warning: Sorting script '{script_path}' does not have a 'get_sort_key' function.")
            return None
    except Exception as e:
        print(f"⚠️  Warning: Failed to load sorting script '{script_path}': {e}")
        return None