# ofmc/plugins.py

import re
from markdown_it import MarkdownIt
from markdown_it.rules_core import StateCore
# from markdown_it.rules_inline import RuleInline
from markdown_it.token import *
from markdown_it.utils import *
from markdown_it.rules_inline import *
from pathlib import Path

WIKILINK_RE = re.compile(r'\[\[([^\]]+)\]\]')

def wikilink_rule(state: StateInline, silent: bool):    # We are looking for [[, but not ![[
    # Check if the previous character is '!'
    if state.pos > 0 and state.src[state.pos - 1] == '!':
        return False

    # Standard check for [[
    if not state.src.startswith('[[', state.pos):
        return False

    match = WIKILINK_RE.match(state.src, state.pos)
    if not match:
        return False

    # In silent mode, we just confirm that the syntax is valid
    if silent:
        return True

    # --- PARSING LOGIC based on user rules ---
    full_target = match.group(1)
    display_text = ""
    # Rule: Check for alias first (e.g., [[note|text]])
    if '|' in full_target:
        parts = full_target.split('|', 1)
        display_text = parts[1]
    # Rule: Check for heading link (e.g., [[note#heading]])
    elif '#' in full_target:
        parts = full_target.split('#', 1)
        display_text = parts[1].lstrip('^') # Remove leading ^ from block refs
    # Rule: Check for block reference (e.g., [[note^abcde]])
    elif '^' in full_target:
        parts = full_target.split('^', 1)
        display_text = parts[0]
    # Default: use the note name itself
    else:
        display_text = full_target

    # Create a new 'wikilink' token
    token = state.push('wikilink', 'a', 0)
    token.content = display_text
    token.meta = {'target': full_target} # Store original target for future use

    # Advance the parser position
    state.pos = match.end()
    return True

def wikilink_plugin(md: MarkdownIt):
    """Plugin for rendering [[wikilinks]] as text."""
    md.inline.ruler.before('link', 'wikilink', wikilink_rule)

CALLOUT_REGEX = re.compile(r"^\s*\[!([a-zA-Z]+)\](.*)")
# Use a non-greedy match for the title to handle titles like "Note-1"
TITLE_BODY_REGEX = re.compile(r"^\s*(\S+)(.*)", re.DOTALL)

def callout_transformer(state: StateCore):
    """
    Scans the token stream and transforms blockquotes into callouts.
    V7: Directly manipulates the token stream (children) instead of re-parsing,
        preserving all nested tokens like math.
    """
    tokens = state.tokens
    i = 0
    while i < len(tokens):
        token = tokens[i]

        if not (token.type == 'blockquote_open' and i + 2 < len(tokens) and
                tokens[i + 1].type == 'paragraph_open' and tokens[i + 2].type == 'inline'):
            i += 1
            continue

        inline_token = tokens[i + 2]
        if not inline_token.children:
            i += 1
            continue

        # We check the content of the first child token to see if it's a callout
        first_line_of_content = inline_token.content.split('\n', 1)[0]
        callout_match = CALLOUT_REGEX.match(first_line_of_content)
        if not callout_match:
            i += 1
            continue

        # --- IT'S A CALLOUT. PERFORM DIRECT TOKEN STREAM MANIPULATION. ---

        callout_type = callout_match.group(1).lower()
        title_line_remainder = callout_match.group(2)

        # 1. Determine title and the prefix string that needs to be removed.
        custom_title = ""
        prefix_to_remove = f"[{callout_match.group(1)}]"

        title_body_match = TITLE_BODY_REGEX.match(title_line_remainder)
        if title_body_match:
            custom_title = title_body_match.group(1)
            # Get prefix length safely by computing how many characters are before group(1)
            index = first_line_of_content.find(title_body_match.group(1))
            if index != -1:
                prefix_to_remove = first_line_of_content[:index + len(custom_title)]
            else:
                prefix_to_remove = first_line_of_content  # fallback
        else:
            prefix_to_remove = first_line_of_content

        # 2. THE CRITICAL FIX: Trim the prefix from the children token list.
        chars_to_trim = len(prefix_to_remove)

        new_children = []
        trimming_done = False
        for child in inline_token.children:
            if trimming_done:
                new_children.append(child)
                continue

            if child.type != 'text':
                new_children.append(child)
                continue

            content_len = len(child.content)
            if content_len <= chars_to_trim:
                chars_to_trim -= content_len
                continue
            else:
                child.content = child.content[chars_to_trim:]
                new_children.append(child)
                trimming_done = True

        inline_token.children = new_children
        inline_token.content = ''.join(child.content for child in new_children)

        # 3. Update the blockquote tokens to callout tokens.
        token.type = 'callout_open';
        token.tag = 'div'
        token.info = callout_type;
        token.meta = {'title': custom_title}

        nesting = 1;
        j = i + 1
        while j < len(tokens):
            if tokens[j].type == 'blockquote_open':
                nesting += 1
            elif tokens[j].type == 'blockquote_close':
                nesting -= 1
            if nesting == 0:
                tokens[j].type = 'callout_close';
                tokens[j].tag = 'div'
                break
            j += 1

        i = j + 1


def callout_plugin(md: MarkdownIt):
    md.core.ruler.push('obsidian_callout', callout_transformer)


# ==============================================================================
#  PLUGIN 2: Block ID Remover
# ==============================================================================

BLOCK_ID_STANDALONE_RE = re.compile(r"^\s*\^([a-fA-F0-9]{6})\s*$")
BLOCK_ID_EOL_RE = re.compile(r"\s+\^([a-fA-F0-9]{6})$")

# def block_id_remover(state: StateCore):
#     """
#     Core plugin to remove Obsidian block IDs (^xxxxxx).
#     - Removes lines that ONLY contain a block ID.
#     - Removes block IDs from the end of other lines.
#     """
#     for token in state.tokens:
#         if token.type != 'inline' or not token.content:
#             continue
#
#         original_content = token.content
#         lines = original_content.split('\n')
#         new_lines = []
#
#         for line in lines:
#             # Rule 1: If a line is just a block ID, skip it
#             if BLOCK_ID_STANDALONE_RE.fullmatch(line):
#                 continue
#
#             # Rule 2: If a line ends with a block ID, strip it
#             cleaned_line = BLOCK_ID_EOL_RE.sub('', line)
#             new_lines.append(cleaned_line)
#
#         new_content = '\n'.join(new_lines)
#
#         # If content was changed, we must re-parse it to update children
#         if new_content != original_content:
#             token.content = new_content
#             new_inline_tokens = state.md.parseInline(new_content, state.env)
#             token.children = new_inline_tokens[0].children if new_inline_tokens and new_inline_tokens[
#                 0].children else []
#
#
# def block_id_plugin(md: MarkdownIt):
#     """Applies the block ID remover as a core rule."""
#     md.core.ruler.push('obsidian_block_id_remover', block_id_remover)

def block_id_processor(state: StateCore):
    """
    Core plugin to find Obsidian block IDs (^xxxxxx), attach a LaTeX label
    to the token's metadata, and then remove the ID from the content.
    """
    registry = state.env.get('link_registry', {})
    current_note = state.env.get('current_note_name', '')

    # 如果不在 book 模式 (没有注册表)，则不执行任何操作
    if not registry or not current_note:
        return

    for token in state.tokens:
        if token.type != 'inline' or not token.content:
            continue

        original_content = token.content
        lines = original_content.split('\n')
        new_lines = []
        found_block_id_in_token = False

        for line in lines:
            # Rule 1: 独立一行的块ID
            if BLOCK_ID_STANDALONE_RE.fullmatch(line.strip()):
                match = BLOCK_ID_STANDALONE_RE.fullmatch(line.strip())
                block_id = match.group(1)
                found_block_id_in_token = True
                # 我们跳过这一行，但标记已找到
                continue

            # Rule 2: 行尾的块ID
            match = BLOCK_ID_EOL_RE.search(line)
            if match:
                block_id = match.group(1)
                target_key = f"{current_note}^{block_id}"
                if target_key in registry:
                    # 找到了！将标签附加到 token 的 meta 中
                    token.meta['latex_label'] = registry[target_key]

                # 清理掉 ID
                cleaned_line = BLOCK_ID_EOL_RE.sub('', line)
                new_lines.append(cleaned_line)
            else:
                new_lines.append(line)

        # 如果是独立一行的ID，我们要确保标签被附加
        if found_block_id_in_token and not token.meta.get('latex_label') and 'block_id' in locals():
            target_key = f"{current_note}^{block_id}"
            if target_key in registry:
                token.meta['latex_label'] = registry[target_key]

        new_content = '\n'.join(new_lines)

        if new_content != original_content:
            token.content = new_content
            # Re-parsing is important if content changes significantly,
            # but for simple removal, just updating content might be enough.
            # Let's keep the robust way.
            new_inline_tokens = state.md.parseInline(new_content, state.env)
            token.children = new_inline_tokens[0].children if new_inline_tokens and new_inline_tokens[
                0].children else []


def block_id_plugin(md: MarkdownIt):
    """Applies the block ID processor as a core rule."""
    md.core.ruler.push('obsidian_block_id_processor', block_id_processor)

# ==============================================================================
#  PLUGIN 3: Highlight (==mark==)
#  (This is the new plugin we are creating from scratch)
# ==============================================================================

def mark_rule(state: StateInline, silent: bool):
    """
    Parses '==' highlighted text '=='.
    """
    if state.src[state.pos:state.pos + 2] != '==':
        return False

    scan_pos = state.pos + 2
    while scan_pos < state.posMax:
        if state.src[scan_pos:scan_pos + 2] == '==':
            if not silent:
                state.push('mark_open', 'mark', 1)

                # --- CORRECTED STATE MANAGEMENT ---
                # 1. Save the original posMax.
                old_pos_max = state.posMax

                # 2. Set new boundaries for the inner tokenizer.
                state.pos += 2
                state.posMax = scan_pos

                # 3. Tokenize the content *inside* the markers.
                state.md.inline.tokenize(state)

                # 4. Restore the original posMax and advance the cursor past the closing marker.
                state.posMax = old_pos_max
                state.pos = scan_pos + 2
                # --- END OF FIX ---

                state.push('mark_close', 'mark', -1)

            return True
        scan_pos += 1

    return False

def mark_plugin(md: MarkdownIt):
    """
    Adds the '==' highlight syntax to markdown-it.
    """
    md.inline.ruler.push('mark', mark_rule)

EMBED_RE = re.compile(r'!\[\[([^\]]+)\]\]')

def embed_rule(state: StateInline, silent: bool):
    match = EMBED_RE.match(state.src, state.pos)
    if not match:
        return False

    full_target = match.group(1).strip()

    if silent:
        state.pos = match.end()
        return True

    # --- Parse the link target ---
    # [[note.md#^blockid|alias]] -> we only care about the part before |
    link_content = full_target.split('|')[0]

    # Split into file and sub-target (e.g., #heading or ^blockid)
    if '#' in link_content:
        file_part, sub_target = link_content.split('#', 1)
        sub_target = '#' + sub_target
    elif '^' in link_content:
        file_part, sub_target = link_content.split('^', 1)
        sub_target = '^' + sub_target
    else:
        file_part = link_content
        sub_target = None

    # --- Resolve the path using the locator ---
    env = getattr(state, 'env', {})
    locator = env.get('locator')
    if not locator:
        return False

    # Obsidian allows omitting .md extension
    resolved_path_str = locator.resolve(file_part) or locator.resolve(f"{file_part}.md")

    if not resolved_path_str:
        # Cannot find file, create a broken link token
        token = state.push('text', '', 0)
        token.content = f"[Broken Embed: {file_part}]"
        state.pos = match.end()
        return True

    resolved_path = Path(resolved_path_str)

    # --- Decide if it's an Image or a Transclusion ---
    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg']
    if resolved_path.suffix.lower() in image_extensions:
        token = state.push('image', '', 0)
        # --- THE FIX IS HERE ---
        # Use a standard Python dictionary instead of AttrDict
        token.attrs = {'src': str(resolved_path), 'alt': ''}
        # --- END OF FIX ---        # Use filename as default caption, extract size from alias if present
        raw_meta = full_target.split('|')[1] if '|' in full_target else None
        token.content = resolved_path.name
        token.meta['wikilink'] = {'raw_meta': raw_meta}
    else:
        # It's a note transclusion
        token = state.push('transclusion', 'div', 0)
        token.meta = {
            'absolute_path': str(resolved_path),
            'sub_target': sub_target,
            'original_link': full_target
        }
        token.content = f"Embedding of {resolved_path.name}"  # For debugging

    state.pos = match.end()
    return True


def embed_plugin(md: MarkdownIt):
    """Plugin for ![[...]] embeds for both images and notes."""
    # Must run before image rule to intercept the syntax
    md.inline.ruler.before('image', 'embed', embed_rule)