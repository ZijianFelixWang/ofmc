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

# ofmc/content_extractor.py

import re
from typing import List, Callable

from markdown_it import MarkdownIt

from .utils import preprocess_nested_blockquotes
from .utils import normalize_unicode
from .utils import fix_callout_formulas
# --- FIX STARTS HERE ---
# Use a standard relative import to get the plugins module
from . import plugins
from .utils import insert_blank_blockquote_lines

# --- FIX ENDS HERE ---

def _heading_to_slug(text: str) -> str:
    """Converts a heading text to a URL-friendly slug."""
    text = text.lower()
    text = ''.join(c if c.isalnum() or c.isspace() else '' for c in text)
    return '-'.join(text.split())


class ContentExtractor:
    def __init__(self, md_content: str, pre_processor_chain: List[Callable[[str], str]]):
        self.md_content = md_content
        self.lines = md_content.splitlines()

        # We need a parser just to analyze the token structure
        md = MarkdownIt("commonmark")

        # --- FIX STARTS HERE ---
        # Correctly apply the plugin using the imported module
        plugins.block_id_plugin(md)
        # --- FIX ENDS HERE ---

        # We don't need to parse with env here, as block_id_plugin works on raw tokens
        self.tokens = md.parse(self.md_content)

        self.pre_processor_chain = pre_processor_chain

    def _run_pre_processing(self, content: str) -> str:
        # 这是一个小型的链运行器
        for process_func in self.pre_processor_chain:
            content = process_func(content)
        return content

    def extract(self, sub_target: str | None) -> str | None:
        """Extracts a slice of Markdown content and applies pre-processing."""

        # 首先获取原始的、未处理的文本块
        raw_result = None
        if not sub_target:
            raw_result = self.md_content
        elif sub_target.startswith(('#^', '^')):
            block_id = sub_target.lstrip('#^')
            raw_result = self._extract_by_block_id(block_id)
        elif sub_target.startswith('#'):
            heading_text = sub_target.lstrip('#')
            raw_result = self._extract_by_heading(heading_text)

        # 如果提取到了内容，就统一在这里运行预处理器
        if raw_result is not None:
            return self._run_pre_processing(raw_result)

        return None

    def _extract_by_block_id(self, block_id: str) -> str | None:
        import re

        pattern = re.compile(rf'\^({re.escape(block_id)})\s*$')
        lines = self.lines

        target_idx = -1
        for i, line in enumerate(lines):
            if pattern.search(line.strip()):
                target_idx = i
                break

        if target_idx == -1:
            return None  # not found

        # Step 1: 向上寻找最近的非空行块（可能是1行，也可能是多行）
        start_idx = target_idx - 1
        while start_idx >= 0 and lines[start_idx].strip() == '':
            start_idx -= 1

        end_idx = start_idx
        while start_idx > 0 and lines[start_idx - 1].strip() != '':
            start_idx -= 1

        # Step 2: 包括 blockid 行本身
        extracted = lines[start_idx:target_idx + 1]

        return '\n'.join(extracted)

    def _extract_by_heading(self, heading_text: str) -> str | None:
        start_token_idx = -1
        start_level = -1

        # Normalize the input heading
        heading_text_norm = heading_text.strip().lower()
        heading_slug = _heading_to_slug(heading_text_norm)

        # Find the starting heading token
        for i, token in enumerate(self.tokens):
            if token.type == 'heading_open':
                content_token = self.tokens[i + 1]
                content_text = content_token.content.strip()
                if (
                        content_text.lower() == heading_text_norm or
                        _heading_to_slug(content_text) == heading_slug
                ):
                    start_token_idx = i
                    start_level = int(token.tag[1])
                    break

        if start_token_idx == -1:
            return None  # Heading not found

        # Find the end of the section
        end_token_idx = len(self.tokens)
        for i in range(start_token_idx + 1, len(self.tokens)):
            token = self.tokens[i]
            if token.type == 'heading_open' and int(token.tag[1]) <= start_level:
                end_token_idx = i
                break

        # Safe line mapping
        start_line = self.tokens[start_token_idx].map[0]
        end_line = None
        if end_token_idx < len(self.tokens):
            # find last token before end that has .map
            for j in range(end_token_idx - 1, start_token_idx, -1):
                if self.tokens[j].map:
                    end_line = self.tokens[j].map[1]
                    break
        if end_line is None:
            end_line = len(self.lines)

        return "\n".join(self.lines[start_line:end_line])
