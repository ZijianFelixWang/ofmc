# ofmc/parser.py
import importlib
from pathlib import Path
from typing import Callable, List

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.texmath import texmath_plugin

from .utils import preprocess_nested_blockquotes
from .utils import normalize_unicode, extract_banner_path
from .utils import insert_blank_blockquote_lines
from .utils import fix_callout_formulas
from .utils import BUILTIN_PRE_PROCESSORS, BUILTIN_POST_PROCESSORS
from .renderer import LatexRenderer
from . import plugins
from .locator import Locator


class OFMCompiler:
    MAX_RECURSION_DEPTH = 5

    def __init__(self, vault_root: str, author: str = "", link_registry: dict = None, build_assets_dir: Path = None, post_processors: list = None, pre_processors: list = None):
        self.vault_root = Path(vault_root).resolve()
        self.link_registry = link_registry or {}
        # 决定是否启用 book 模式的链接功能
        self.book_mode = bool(self.link_registry)

        self.build_assets_dir = build_assets_dir

        # Pass the compiler instance to the renderer for recursive calls
        self.author = author
        self.post_processors = post_processors or []
        self.pre_processors = pre_processors or []

        self.pre_processor_chain = self._load_processor_chain(
            self.pre_processors, BUILTIN_PRE_PROCESSORS, "pre_processor"
        )
        self.post_processor_chain = self._load_processor_chain(
            self.post_processors, BUILTIN_POST_PROCESSORS, "post_processor"
        )

        self.renderer = LatexRenderer(self, self.link_registry, self.book_mode)

        self.md = (
            MarkdownIt("commonmark", {"breaks": True})
            .enable("table")
            .use(texmath_plugin, delimiters='dollars')
        )

        # Apply our custom plugins
        plugins.callout_plugin(self.md)
        plugins.mark_plugin(self.md)
        plugins.embed_plugin(self.md)  # Use the new embed plugin
        plugins.wikilink_plugin(self.md)
        plugins.block_id_plugin(self.md)

    @staticmethod
    def _load_processor_chain(names: List[str], builtin_registry: dict, chain_type: str) -> List[Callable[[str], str]]:
        # 这是一个通用的加载器，可以加载任何类型的处理器链
        chain = []
        for name in names:
            if name.startswith('$'):
                func_name = name[1:]
                if func_name in builtin_registry:
                    chain.append(builtin_registry[func_name])
                else:
                    print(f"Warning: Unrecognized built-in processor: {chain_type} '{name}'，Ignored.")
            elif ":" in name:
                try:
                    path_str, func_name = name.split(":", 1)
                    # 路径相对于项目根目录（config.toml 所在位置）
                    script_path = path_str

                    spec = importlib.util.spec_from_file_location(name, script_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    func = getattr(module, func_name)
                    chain.append(func)
                except Exception as e:
                    print(f"Warning: Cannot load processor: '{name}': {e}")
            else:
                print(f"Warning: Unrecognized processor: '{name}'，Ignored.")
        return chain

    @staticmethod
    def _run_chain(content: str, chain: List[Callable[[str], str]]) -> str:
        """通用管道运行器"""
        for process_func in chain:
            content = process_func(content)
        return content

    def compile(self, input_file: str, mode: str = 'standalone') -> str:
        """Public method to compile a file into a full LaTeX document."""
        input_path = Path(input_file).resolve()
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                markdown_text = f.read()
        except FileNotFoundError:
            raise

        markdown_text, banner_path = extract_banner_path(markdown_text)
        # markdown_text = (
        #     normalize_unicode(
        #         insert_blank_blockquote_lines(
        #             fix_callout_formulas(
        #                 preprocess_nested_blockquotes(markdown_text)
        #             )
        #         )
        #     )
        # )
        #markdown_text = (markdown_text)
        #markdown_text = insert_blank_blockquote_lines(markdown_text)

        markdown_text = self._run_chain(markdown_text, self.pre_processor_chain)

        # StartError embedding include.md: Target not found in file. the compilation with recursion depth 0
        body_content = self._compile_body(markdown_text, input_path, 0)

        # Wrap the body with the preamble and postamble
        title = input_path.stem

        locator = Locator(self.vault_root, input_path)

        raw_doc = self.renderer.render_document(body_content,
                                             title=title,
                                             author=self.author,
                                             banner_path=banner_path,
                                             locator=locator,
                                             mode=mode)

        return self._run_chain(raw_doc, self.post_processor_chain)

    def _compile_body(self, markdown_text: str, current_file: Path, recursion_depth: int) -> str:
        """
        Protected method to compile Markdown text into a LaTeX body snippet.
        This is used for recursive calls.
        """
        if recursion_depth > self.MAX_RECURSION_DEPTH:
            return r"\textcolor{red}{\textbf{Error: Max recursion depth reached.}}"

        # Each compilation needs a locator relative to its own file path
        locator = Locator(self.vault_root, current_file)

        # Pass necessary data through the environment
        env = {
            'locator': locator,
            'recursion_depth': recursion_depth,
            'current_file': current_file,
            'current_note_name': current_file.stem,  # 添加笔记名，方便插件和渲染器使用
            'link_registry': self.link_registry,  # 传递注册表
            'in_callout': 0,
            'build_assets_dir' : self.build_assets_dir,
        }

        if recursion_depth > 0:
            env['in_tcolorbox'] = True

        tokens: list[Token] = self.md.parse(markdown_text, env)
        return self.renderer.render_tokens(tokens, env)
