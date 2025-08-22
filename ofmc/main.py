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

# ofmc/main.py
import argparse
import os
import sys
import shutil
import uuid
from art import *
from pathlib import Path
from .parser import OFMCompiler
from .config import load_config
from .batch_compiler import run_batch_compilation, run_xelatex, get_temp_dir

import colorama
from colorama import Fore, Style

def main():
    """
    Main execution function using the config.toml file.
    """

    colorama.init()

    # 1. 设置命令行参数解析器g
    #    - description 会在用户使用 -h 或 --help 时显示，非常有用。
    parser = argparse.ArgumentParser(
        description="A powerful batch compiler for Obsidian notes, converting them to professional PDFs via LaTeX."
    )

    # 2. 添加 --config 参数
    #    - "-c", "--config" 定义了短名称和长名称。
    #    - "dest='config_path'" 指定了存储解析结果的变量名。
    #    - "default='config.toml'" 实现了你的核心需求：如果没有指定，则回退到'config.toml'。
    #    - "help" 提供了清晰的文档。
    #    - "type=Path" 是一个很好的实践，argparse会自动将字符串转换为pathlib.Path对象。
    parser.add_argument(
        "-c", "--config",
        dest="config_path",
        default="config.toml",
        type=Path,
        help="Path to the configuration file (default: %(default)s)"
    )

    args = parser.parse_args()

    tprint("ofmc", "isometric1")
    print("OFMC Obsidian-Flavored Markdown to LaTeX compiler.")

    # 3. 使用解析出的路径加载配置
    #    - 之前的硬编码 "config.toml" 被替换为 args.config_path
    config_file = args.config_path
    print(f"Attempting to load configuration from: {config_file.resolve()}")

    # Load configuration from config.toml (this part is correct and unchanged)
    try:
        cfg = load_config(config_file)
    except (FileNotFoundError, KeyError, NotADirectoryError, ValueError, TypeError) as e:
        print(f"❌ Configuration Error: {e}")
        sys.exit(1)

    # --- DISPATCHER LOGIC ---
    if cfg.batch_compile:
        # --- BATCH MODE ---
        print("Batch compilation enabled. Starting batch process...")
        try:
            run_batch_compilation(cfg)
        except Exception as e:
            print(f"\nAn unexpected error occurred during batch compilation: {e}")
            import traceback
            traceback.print_exc()

    else:
        # --- SINGLE FILE MODE (Original Logic) ---
        temp_dir = get_temp_dir()
        print(f"Using temporary directory for compilation: {temp_dir}")

        try:
            output_dir = cfg.output_dir
            build_assets_dir = output_dir / "build_assets"
            os.makedirs(build_assets_dir, exist_ok=True)

            # 1. Compile Markdown to a LaTeX string in memory
            compiler = OFMCompiler(
                vault_root=str(cfg.vault_root),
                author=cfg.author,
                pre_processors=cfg.pre_processors,
                post_processors=cfg.post_processors,
                build_assets_dir=build_assets_dir
            )
            latex_result = compiler.compile(str(cfg.markdown_file))

            output_tex_path = cfg.markdown_file.with_suffix(".tex")
            output_tex_path.write_text(latex_result, encoding='utf-8')
            print(f"Intermediate .tex file written to: {output_tex_path}")

            # 2. Write the .tex file to the temporary directory with a safe name
            temp_tex_name = f"{uuid.uuid4()}.tex"
            temp_tex_path = temp_dir / temp_tex_name
            temp_tex_path.write_text(latex_result, encoding='utf-8')

            # 3. Run XeLaTeX in the isolated directory. run_xelatex now returns True/False.
            if run_xelatex(temp_tex_path, temp_dir):
                # 4. If successful, copy the resulting PDF back to the original location
                source_pdf_path = temp_tex_path.with_suffix('.pdf')
                final_pdf_path = cfg.markdown_file.with_suffix('.pdf')

                shutil.copy2(source_pdf_path, final_pdf_path)
                print(f"✅ Successfully compiled. PDF output is at: {final_pdf_path}")
            else:
                # The run_xelatex function already prints detailed logs
                print(f"❌ Compilation failed. Please check the logs above.")

        except Exception as e:
            print(f"An unexpected error occurred during the compilation process: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # 5. ALWAYS clean up the temporary directory
            print(f"Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    main()
