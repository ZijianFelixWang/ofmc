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

# ofmc/__init__.py

"""
OFMC - Obsidian-Flavored Markdown Compiler
A powerful batch compiler for Obsidian notes to professional PDFs via LaTeX.
"""

# 1. 定义包的版本号，这是一个非常好的习惯
__version__ = "1.0.0"

# 2. 从子模块中“提升”核心的类和函数到包的顶层命名空间
from .config import load_config
from .batch_compiler import run_batch_compilation, run_xelatex, get_temp_dir
from .parser import OFMCompiler

__all__ = [
    'load_config',
    'run_batch_compilation',
    'run_xelatex',
    'get_temp_dir',
    'OFMCompiler'
    '__version__'
]