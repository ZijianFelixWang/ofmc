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