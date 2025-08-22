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

# ofmc/renderer.py
import hashlib
import importlib
import re
import shutil
import urllib
from pathlib import Path

from .utils import get_shared_latex_preamble
# from .utils import replace_custom_arrow_tricks, replace_bbox, fix_choose
# from .utils import fix_kern_syntax
# from .utils import fix_smaller_than
# from .utils import replace_array_with_matrix_environments
# from .utils import fix_mathbb_k
from .utils import replace_tagged_dollars, split_inline_display_math
# from .utils import fix_align_environment
from .utils import demote_headings
# from .utils import fix_tcolorbox_label_tcolorbox
from .utils import BUILTIN_POST_PROCESSORS

from .content_extractor import ContentExtractor
from markdown_it.token import Token

import colorama
from colorama import Fore, Style

# Forward declaration for type hinting to avoid circular import error
from typing import TYPE_CHECKING, List, Callable

if TYPE_CHECKING:
    from .parser import OFMCompiler

def escape_latex(text: str) -> str:
    """
    Escapes characters with special meaning in LaTeX.
    """
    # This mapping is crucial for correctness.
    replacements = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '\\': r'\textbackslash{}',
        '<': r'\textless{}',
        '>': r'\textgreater{}',
    }
    # Use a regex to perform all replacements in one go.
    # This is more efficient and correct than chained .replace().
    # The regex pattern is created by joining the escaped keys.
    regex = re.compile('|'.join(re.escape(key) for key in replacements.keys()))
    return regex.sub(lambda match: replacements[match.group(0)], text)
    #return text

class LatexRenderer:
    """
    Renders a markdown-it token stream to a LaTeX document string.
    """
    def __init__(self, compiler: 'OFMCompiler', link_registry: dict = None, book_mode: bool = False):
        # Keep a reference to the compiler to make recursive calls
        self.compiler = compiler

        self.link_registry = link_registry or {}
        self.book_mode = book_mode

    CALLOUT_COLORS = {
        'note': 'blue',
        'abstract': 'cyan',
        'info': 'cyan',
        'todo': 'orange',
        'tip': 'green',
        'done': 'green',
        'question': 'orange',
        'warning': 'red',
        'caution': 'red',
        'fail': 'red',
        'error': 'red',
        'example': 'violet',
        'cite': 'gray',
    }

    def render_tokens(self, tokens: list[Token], env: dict) -> str:
        """Renders a list of block tokens into a LaTeX string (body only)."""
        output = []

        # --- STATE MANAGEMENT VARIABLES ---
        in_table = False
        table_current_col = 0
        in_header = False

        skip_until_index = -1

        # Main rendering loop
        for i, token in enumerate(tokens):
            # --- Check if we should skip this token ---
            if i <= skip_until_index:
                continue

            if token.type == 'heading_open':
                level = int(token.tag[1:])
                # --- 获取标题文本 ---
                # heading_open 后面紧跟着一个 inline token，它的内容就是标题
                inline_token = tokens[i + 1]
                # 我们需要渲染它以处理其中的 markdown，例如 `code`
                heading_content = self.render_inline_content_only(inline_token.children, env)

                section_map = {1: r'\section', 2: r'\subsection', 3: r'\subsubsection'}
                output.append(f"{section_map.get(level, r'\paragraph')}{{{heading_content}}}")

                # +++ 新增：放置标题锚点 +++
                if self.book_mode:
                    current_note = env.get('current_note_name', '')
                    # 需要用原始文本来匹配，而不是渲染后的
                    original_heading_text = inline_token.content.strip()
                    target_key = f"{current_note}#{original_heading_text}"
                    if target_key in self.link_registry:
                        label = self.link_registry[target_key]
                        output.append(f"\\label{{{label}}}")

                # 4. Add spacing after the heading block
                output.append("\n\n")

                # 5. --- Crucially, tell the loop to skip the processed tokens ---
                # We have processed tokens at index i, i+1, and i+2.
                # The next iteration should start at i+3.
                skip_until_index = i + 2

            elif token.type == 'heading_close':
                output.append("\n\n")  # 仅换行，不再需要闭合括号

            elif token.type == 'paragraph_open':
                # LaTeX handles paragraphs with double newlines.
                # We only add a newline at the end.
                pass
            elif token.type == 'paragraph_close':
                # +++ 修改：在段落结束时检查并放置块ID锚点 +++
                # paragraph_open 之前的 token 是 inline token
                inline_token = tokens[i-1]
                if self.book_mode and inline_token.meta.get('latex_label'):
                    output.append(f"\\label{{{inline_token.meta['latex_label']}}}")
                output.append("\n\n")

            elif token.type == 'inline':
                itc = env.get("in_tcolorbox", False)
                if env.get('in_callout', 0) > 0:
                    itc = True
                self._render_inline(token, output, env, in_tcolorbox=itc)

            elif token.type == 'fence':
                lang = token.info.split(' ')[0] if token.info else ""
                # For now, we use verbatim. Listings package would be better for syntax highlighting.
                output.append(f"\\begin{{verbatim}}\n{token.content.strip()}\n\\end{{verbatim}}\n\n")

            elif token.type == 'bullet_list_open':
                output.append("\\begin{itemize}\n")
            elif token.type == 'bullet_list_close':
                output.append("\\end{itemize}\n\n")
            
            elif token.type == 'ordered_list_open':
                output.append("\\begin{itemize}\n")
            elif token.type == 'ordered_list_close':
                output.append("\\end{itemize}\n\n")

            elif token.type == 'list_item_open':
                output.append(r"\item ")
            elif token.type == 'list_item_close':
                output.append("\n")

            elif token.type == 'table_open':
                # ALWAYS use tabularx for robust, wrapping tables.
                # This simplifies logic and prevents page overflow.

                num_cols = 0
                # Look ahead to count columns.
                for j in range(i + 1, len(tokens)):
                    if tokens[j].type == 'tr_open':
                        for k in range(j + 1, len(tokens)):
                            if tokens[k].type == 'th_open':
                                num_cols += 1
                            elif tokens[k].type == 'tr_close':
                                break
                        break

                if num_cols > 0:
                    # Heuristic: First column 'l' (non-wrapping), rest 'X' (wrapping).
                    # This works well for identifier/description tables.
                    if num_cols == 1:
                        col_specs = ['X']  # A single column MUST be X to wrap
                    else:
                        col_specs = ['l'] + ['X'] * (num_cols - 1)

                    col_spec = ' '.join(col_specs)

                    output.append(f"\\begin{{tabularx}}{{\\textwidth}}{{ {col_spec} }}\n\\toprule\n")
                    in_table = True
                else:
                    in_table = False

            elif token.type == 'table_close':
                if not in_table: continue
                # ALWAYS close with tabularx, matching the open tag.
                output.append("\\bottomrule\n\\end{tabularx}\n\n")
                in_table = False

            elif token.type == 'thead_open':
                if not in_table: continue
                in_header = True

            elif token.type == 'thead_close':
                if not in_table: continue
                output.append("\\midrule\n")  # Line between header and body
                in_header = False

            elif token.type == 'tbody_open':
                if not in_table: continue
                table_current_col = 0  # Reset for the body

            elif token.type == 'tr_open':
                if not in_table: continue
                table_current_col = 0  # Reset for each new row

            elif token.type == 'tr_close':
                if not in_table: continue
                output.append(" \\\\\n")  # End of a row

            elif token.type == 'th_open' or token.type == 'td_open':
                if not in_table: continue
                table_current_col += 1
                if table_current_col > 1:
                    output.append(" & ")
                if token.type == 'th_open':
                    output.append("\\textbf{")  # Make headers bold

            elif token.type == 'th_close':
                if not in_table: continue
                output.append("}")  # Close \textbf

            # td_close requires no action
            # --- END: ROBUST TABLE RENDERING LOGIC ---

            # +++ ADDED RULE FOR REGULAR BLOCKQUOTES +++
            elif token.type == 'blockquote_open':
                output.append("\\begin{quote}\n")
            elif token.type == 'blockquote_close':
                output.append("\\end{quote}\n\n")

            elif token.type == 'callout_open':
                callout_type = token.info
                title = token.meta.get('title')

                # Default to the type itself if no specific title is given
                if not title:
                    title = callout_type.capitalize()

                color = self.CALLOUT_COLORS.get(callout_type, 'gray')

                env['in_callout'] = env.get('in_callout', 0) + 1

                # Construct the tcolorbox environment
                # Note the use of f-string and braces to generate LaTeX code
                output.append(
                    f"\\begin{{tcolorbox}}["
                    f"colback={color}!5!white, "
                    f"colframe={color}!75!black, coltext=black,"
                    f"fonttitle=\\bfseries, breakable, "
                    f"title={{{escape_latex(title)}}}"  # Escape the title text
                    f"]\n"
                )
            elif token.type == 'callout_close':
                env['in_callout'] = max(0, env.get('in_callout', 0) - 1)
                output.append("\\end{tcolorbox}\n\n")

        return "".join(output)

    def render_inline_content_only(self, children: list[Token], env: dict) -> str:
        """
        一个简化的 _render_inline，它将一系列 inline token 渲染成一个字符串。
        现在支持文本、代码、粗体、斜体和行内公式。
        """
        temp_output = []
        for child in children:
            if child.type == 'text':
                temp_output.append(escape_latex(child.content))
            elif child.type == 'strong_open':
                temp_output.append(r"\textbf{")
            elif child.type == 'strong_close':
                temp_output.append("}")
            elif child.type == 'em_open':
                temp_output.append(r"\textit{")
            elif child.type == 'em_close':
                temp_output.append("}")
            elif child.type == 'code_inline':
                temp_output.append(r"\texttt{" + escape_latex(child.content) + "}")
            # --- 新增的公式支持 ---
            elif child.type == 'math_inline':
                # texmath_plugin 已经处理好了内容，我们只需加上 $
                temp_output.append(f"${child.content}$")
            # 你可以根据需要添加更多 token 类型

        return "".join(temp_output)

    def _render_inline(self, token, output: list, env: dict, in_tcolorbox: bool = False):
        if not token.children:
            output.append(escape_latex(token.content))
            #output.append(token.content)
            return

        for child in token.children:
            if child.type == 'text':
                output.append(escape_latex(child.content))
                #output.append(child.content)
            elif child.type == 'strong_open':
                output.append(r"\textbf{")
            elif child.type == 'strong_close':
                output.append("}")
            elif child.type == 'em_open':
                output.append(r"\textit{")
            elif child.type == 'em_close':
                output.append("}")
            # --- MODIFICATION START ---
            elif child.type == 'mark_open':
                output.append(r"\hl{")
            elif child.type == 'mark_close':
                output.append("}")
            # --- MODIFICATION END ---

            elif child.type == 'wikilink':
                escaped_content = escape_latex(child.content)

                if not self.book_mode:
                    output.append(f"\\textcolor{{blue}}{{{escaped_content}}}")
                else:
                    # --- START: FINALIZED LINKING LOGIC ---

                    # original_target can be "Note#^id|alias"
                    original_target = child.meta.get('target', '')

                    # Step 1: CRITICAL FIX - Strip the alias part.
                    # The actual link target is everything before the first '|'.
                    # If no '|' exists, this safely returns the original string.
                    link_path = original_target.split('|', 1)[0]

                    # Step 2: Initialize lookup_key with the clean path.
                    lookup_key = link_path

                    # Step 3: Prepend current note if link is local (e.g., [[#A Heading]])
                    if link_path.startswith(('#', '^')):
                        current_note = env.get('current_note_name', '')
                        lookup_key = f"{current_note}{link_path}"

                    # Step 4: Normalize the "note#^id" format to our canonical "note^id".
                    if '#^' in lookup_key:
                        lookup_key = lookup_key.replace('#^', '^', 1)

                    # Now, lookup_key is fully canonical and ready for lookup.
                    if lookup_key in self.link_registry:
                        label = self.link_registry[lookup_key]
                        output.append(f"\\hyperref[{label}]{{{escaped_content}}}")
                        # print(f"{Fore.CYAN} OK [DEBUG] Found key [[{original_target}]] in note '{env.get('current_note_name', '')}' with look up key '{lookup_key}' successfully.{Style.RESET_ALL}")
                    else:
                        # The warning remains for genuinely broken links.
                        #print(
                        #    f"{Fore.YELLOW}⚠️  [Warning] Broken link found: [[{original_target}]] in note '{env.get('current_note_name', '')}' (Lookup key: '{lookup_key}'){Style.RESET_ALL}")
                        output.append(f"\\textcolor{{red}}{{{escaped_content}}}")
                    # --- END: FINALIZED LINKING LOGIC ---

            elif child.type == 'code_inline':
                output.append(r"\texttt{" + escape_latex(child.content) + "}")
            elif child.type == 'math_inline':
                output.append(f"${child.content}$")

            elif child.type == 'image':
                # --- Step 1: Get original data from token (your code) ---
                original_src = child.attrs.get('src', '')
                caption = escape_latex(child.content)

                # --- Step 2: Resolve path and create a unique, safe asset path ---
                # Decode URL-encoded characters like '%20' for spaces
                decoded_src = urllib.parse.unquote(original_src)

                # Skip web URLs, as we can't process them locally
                if decoded_src.startswith(('http://', 'https://')):
                    output.append(f"\\textcolor{{red}}{{Web image skipped: {escape_latex(decoded_src)}}}")
                    continue

                # Get necessary paths from the environment dictionary
                current_file: Path = env['current_file']
                build_assets_dir: Path = env['build_assets_dir']

                # Resolve the src path to an absolute path
                if Path(decoded_src).is_absolute():
                    abs_src_path = Path(decoded_src)
                else:
                    # Relative paths are relative to the current note's directory
                    abs_src_path = (current_file.parent / decoded_src).resolve()

                # Safety check: if the source image doesn't exist, report error and skip
                if not abs_src_path.exists():
                    output.append(f"\\textcolor{{red}}{{Image not found: {escape_latex(str(abs_src_path))}}}")
                    continue

                # Create a unique filename using a hash of its absolute path
                # This is the key to solving the name collision problem
                path_hash = hashlib.sha1(str(abs_src_path).encode('utf-8')).hexdigest()
                unique_filename = f"{path_hash}{abs_src_path.suffix}"

                # Define the destination path in the build's 'assets' directory
                dest_path = build_assets_dir / unique_filename

                # Copy the file only if it doesn't already exist in the destination
                if not dest_path.exists():
                    shutil.copyfile(abs_src_path, dest_path)

                # This is the new, safe path that LaTeX will use (e.g., "assets/a1b2c3d4.svg")
                new_latex_path = build_assets_dir / unique_filename

                # --- Step 3: Use your existing logic for width and command generation ---
                # 1. Start with a default width (your code)
                width_option = "width=0.4\\textwidth"

                # 2. Check for custom size in metadata (your code)
                wikilink_meta = child.meta.get('wikilink', {}).get('raw_meta')
                if wikilink_meta and wikilink_meta.strip().isdigit():
                    try:
                        obsidian_size = int(wikilink_meta.strip())
                        converted_size = (obsidian_size * 190) // 390
                        final_size = min(converted_size, 350)
                        width_option = f"width={final_size}pt"
                    except ValueError:
                        pass  # Fallback to default if conversion fails

                # 3. Build the LaTeX command, but with the NEW, SAFE path
                # We check the suffix of the ORIGINAL file to decide the command
                if abs_src_path.suffix.lower() == '.svg':
                    image_cmd = f"\\includesvg[{width_option}]{{{str(new_latex_path)}}}"
                else:
                    image_cmd = f"\\includegraphics[{width_option}]{{{str(new_latex_path)}}}"

                if in_tcolorbox:
                    output.append(
                        f"\n\\begin{{center}}\n{image_cmd}\n\n"
                        f"\\textit{{{caption}}}\n\\end{{center}}\n"
                    )
                else:
                    output.append(
                        f"\n\\begin{{figure}}[h!]\n"
                        f"\\centering\n"
                        f"{image_cmd}\n"
                        f"\\caption{{{caption}}}\n"
                        f"\\end{{figure}}\n"
                    )

            elif child.type == 'transclusion':
                meta = child.meta
                try:
                    with open(meta['absolute_path'], 'r', encoding='utf-8') as f:
                        content = f.read()

                    extractor = ContentExtractor(content, pre_processor_chain=self.compiler.pre_processor_chain)
                    sliced_md = extractor.extract(meta['sub_target'])

                    if sliced_md is None:
                        raise ValueError("Target not found in file.")

                    # --- RECURSIVE CALL ---
                    new_depth = env.get('recursion_depth', 0) + 1
                    child_tex = self.compiler._compile_body(
                        sliced_md, Path(meta['absolute_path']), new_depth
                    )

                    child_tex = demote_headings(child_tex)
                    child_tex = replace_tagged_dollars(split_inline_display_math((child_tex)))

                    # Wrap the embedded content in a styled box
                    output.append(
                        f"\\begin{{tcolorbox}}["
                        f"colback=black!5!white, colframe=black!75!white, coltext=black,"
                        f"title={{{escape_latex(Path(meta['absolute_path']).name)}}}, "
                        f"breakable, "
                        f"fonttitle=\\small\\ttfamily]\n"
                        f"{child_tex}\n"
                        f"\\end{{tcolorbox}}\n"
                    )

                except Exception as e:
                    output.append(f"\\textcolor{{red}}{{\\textbf{{Error embedding "
                                  f"{escape_latex(Path(meta['absolute_path']).name)}}}: {escape_latex(str(e))}}}")

            # +++ THE FINAL, CRITICAL FIX +++
            # Add this block right after 'math_inline'
            elif child.type == 'math_single':
                # Render single-char math exactly like inline math
                output.append(f"${escape_latex(child.content)}$")
            # ++++++++++++++++++++++++++++++++

            elif child.type == 'math_block': # Sometimes parsed as an inline child
                 output.append(f"\\[\n{child.content}\n\\]")
            elif child.type == 'softbreak':
                output.append(" ") # Treat softbreaks as spaces
            elif child.type == 'hardbreak':
                output.append("\\\\\n") # Hard line break

    def render_document(self,
                        body_content: str,
                        title: str = "Untitled",
                        author: str = "Anonymous!",
                        banner_path: str = None,
                        locator = None,
                        mode: str = 'standalone') -> str:
        """Wraps the body content with the LaTeX preamble and closing tags."""

        # mode: 'standalone' for a full document, 'chapter' for a book chapter.

        banner_latex = ""
        if banner_path:
            if not locator:
                return False
            resolved_path_str = locator.resolve(banner_path) or locator.resolve(f"{banner_path}.png")
            banner_path = Path(resolved_path_str)

        if banner_path:
            banner_latex = f"""
        \\begin{{center}}
            \\includegraphics[width=0.9\\textwidth]{{{banner_path}}}
        \\end{{center}}
        \\vspace{{1em}}
        """

        preamble = f"""
        \\documentclass[a4paper, 11pt]{{article}}
        {get_shared_latex_preamble()}
        
        \\usepackage[a4paper, top=1in, bottom=1in, left=0.9in, right=0.9in]{{geometry}}
        """

        if mode == "standalone":
            doc = f"""{preamble}
            \\title{{{title}}}
            \\author{{{author}}}
            \\date{{\\today}}
            \\begin{{document}}
            \\maketitle
            {banner_latex}
            \\tableofcontents
            
            {body_content}
            
            \\end{{document}}"""
        elif mode == "chapter":
            chapter_title = title
            doc = f"""\\chapter{{{chapter_title}}}
            
            {banner_latex}
            \\vspace{{1cm}}
            {body_content}
            
            """
        else:
            raise ValueError(f"Unknown rendering mode: {mode}")

        # return (
        #     fix_tcolorbox_label_tcolorbox(
        #         fix_choose(
        #             replace_bbox(
        #                 replace_array_with_matrix_environments(
        #                     fix_kern_syntax(
        #                         fix_smaller_than(
        #                             fix_mathbb_k(
        #                                 replace_tagged_dollars(
        #                                     split_inline_display_math(
        #                                         replace_custom_arrow_tricks(
        #                                             fix_align_environment(doc)
        #                                         )
        #                                     )
        #                                 )
        #                             )
        #                         )
        #                     )
        #                 )
        #             )
        #         )
        #     )
        # )

        return doc
