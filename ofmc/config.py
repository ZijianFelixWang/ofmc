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

# ofmc/config.py

import tomli
from tomli import TOMLDecodeError
from pathlib import Path
from typing import Optional, List

class Config:
    """Holds the application configuration."""
    def __init__(self,
                 vault_root: Path,
                 markdown_file: Optional[Path] = None,
                 author: str = "Who am I?",
                 batch_compile: bool = False,
                 output_dir: Path = Path("./output"),
                 excluded=None,
                 enable_simple_merge: bool = True,
                 enable_book_compile: bool = False,
                 book_title: str = "Untitled Book",
                 book_parts: list = None,
                 front_matter: list = None,
                 back_matter: list = None,
                 cover_image: Optional[Path] = None,
                 sorting_script: Optional[Path] = None,
                 post_processors: Optional[List[str]] = None,
                 pre_processors: Optional[List[str]] = None):
        self.vault_root = vault_root
        self.markdown_file = markdown_file
        self.author = author
        self.batch_compile = batch_compile
        self.output_dir = output_dir
        self.excluded = excluded
        self.enable_simple_merge = enable_simple_merge
        self.enable_book_compile = enable_book_compile
        self.book_title = book_title
        self.book_parts = book_parts or []
        self.front_matter = front_matter or []
        self.back_matter = back_matter or []
        self.cover_image = cover_image
        self.sorting_script = sorting_script
        self.post_processors = post_processors or []
        self.pre_processors = pre_processors or []

def load_config(config_path: str = "config.toml") -> Config:
    """
    Loads configuration from a TOML file with conditional validation.
    """
    config_file = Path(config_path)
    if not config_file.is_file():
        raise FileNotFoundError(f"Config file not found: {config_file.resolve()}")

    try:
        with open(config_file, "rb") as f:
            data = tomli.load(f)
    except TOMLDecodeError as e:
        # 当 TOML 文件格式错误时，抛出一个更通用的 ValueError，并附带清晰信息
        # "from e" 会保留原始异常的堆栈，便于调试，但用户看到的是我们的友好信息
        raise ValueError(f"Error parsing '{config_file.name}': The file is not a valid TOML. Details: {e}") from e

    try:
        # --- 步骤 1: 加载所有可能的值 ---
        vault_root = Path(data["vault_root"]).expanduser()
        author = str(data.get("author", "Anonymous"))
        batch_compile = data.get("batch_compile", False)
        output_dir = Path(data.get("output_dir", "./output")).expanduser()
        excluded = data.get("excluded", [])
        enable_simple_merge = data.get("enable_simple_merge", True)
        enable_book_compile = data.get("enable_book_compile", False)
        book_title = data.get("book_title", "Untitled Book")
        book_parts = data.get("book_parts", [])
        front_matter = data.get("front_matter", [])
        back_matter = data.get("back_matter", [])

        cover_image_str = data.get("cover_image")  # 获取字符串，如果不存在则为 None
        # 如果提供了路径字符串，就将其解析为相对于 vault 根目录的完整路径
        cover_image = vault_root / cover_image_str if cover_image_str else None

        processor_config = data.get("processors", {})
        post_processors = processor_config.get("post", [])
        pre_processors = processor_config.get("pre", [])

        sorting_script_str = data.get("sorting_script")
        sorting_script = config_file.parent / sorting_script_str if sorting_script_str else None

    except KeyError as e:
        # vault_root 是唯一在任何模式下都必须存在的键
        raise KeyError(f"Missing required key in config file: {e}")

    # --- 步骤 2: 验证通用路径 ---
    if not vault_root.is_dir():
        raise NotADirectoryError(f"Vault root is not a valid directory: {vault_root}")

    # --- 步骤 3: 根据模式进行条件加载和验证 ---
    markdown_file = None
    if not batch_compile:
        try:
            markdown_file_str = data["markdown_file"]
        except KeyError:
            # 在单文件模式下，这个键是必须的
            raise KeyError("Missing 'markdown_file' key, required when 'batch_compile' is false.")

        markdown_file = Path(markdown_file_str).expanduser()
        if not markdown_file.is_file():
            raise FileNotFoundError(f"Markdown file not found for single-file compilation: {markdown_file}")

    # --- 步骤 4: 创建并返回 Config 对象 ---
    return Config(
        vault_root=vault_root,
        markdown_file=markdown_file,
        author=author,
        batch_compile=batch_compile,
        output_dir=output_dir,
        excluded=excluded,
        enable_simple_merge=enable_simple_merge,
        enable_book_compile=enable_book_compile,
        book_title=book_title,
        book_parts=book_parts,
        front_matter=front_matter,
        back_matter=back_matter,
        cover_image=cover_image,
        sorting_script=sorting_script,
        post_processors=post_processors,
        pre_processors=pre_processors,
    )