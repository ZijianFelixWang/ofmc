
```
      ___           ___           ___           ___
     /\  \         /\  \         /\__\         /\  \
    /::\  \       /::\  \       /::|  |       /::\  \
   /:/\:\  \     /:/\:\  \     /:|:|  |      /:/\:\  \
  /:/  \:\  \   /::\~\:\  \   /:/|:|__|__   /:/  \:\  \
 /:/__/ \:\__\ /:/\:\ \:\__\ /:/ |::::\__\ /:/__/ \:\__\
 \:\  \ /:/  / \/__\:\ \/__/ \/__/~~/:/  / \:\  \  \/__/
  \:\  /:/  /       \:\__\         /:/  /   \:\  \
   \:\/:/  /         \/__/        /:/  /     \:\  \
    \::/  /                      /:/  /       \:\__\
     \/__/                       \/__/         \/__/

```

# OFMC: Obsidian-Flavored Markdown Compiler
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0) [![Python Version](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)

`ofmc` is a compiler that converts Markdown files with Obsidian-specific syntax into high-quality PDFs using XeLaTeX. It is designed to handle single files or an entire Obsidian vault, with support for parallel processing and the creation of a single, unified PDF book from multiple notes.

**Note.** Google Gemini 2.5 is used in writing this `readme` and in the programming process.

---

## Core Functionality

#### Obsidian Syntax Conversion
`ofmc` understands and converts a wide range of Obsidian's extended Markdown syntax:
*   **Wikilinks**: Converts `[[...]]` to clickable intra-document PDF links.
    *   Supports aliased links: `[[Using Spectral Sequences#Fibration and Path Fibration|path fibration]]`
    *   Supports block reference links: `[[Hilbert Nullstellensatz#^72f6c0|finite-type]]`
*   **Transclusions**: Embeds content from other notes using `![[...]]`.
    *   Supports heading selectors: `![[My Note#A Specific Section]]`
    *   Supports block selectors: `![[My Note#^a1b2c3]]`
*   **Mathematics**: Full support for inline (`$...$`) and display (`$$...$$`) LaTeX math environments.
*   **Images & SVGs**: Renders local images, including Obsidian's `|width` pipe syntax for scaling. SVGs are converted to PDF via Inkscape for vector-perfect quality.
*   **Callouts**: Translates Obsidian's callout blocks (`> [!INFO]`) into `tcolorbox` environments, with support for nested callouts.
*   **Extended Markdown**: Correctly processes tables, highlights (`==...==`), and URL links.

#### Compilation Modes
*   **Single File Compilation**: Compile a single Markdown file to a PDF.
*   **Vault Compilation**: Process an entire vault in parallel, respecting user-defined exclusion rules.
*   **PDF Book Generation**: Assemble multiple compiled `.tex` files into a master document to produce a single, cohesive PDF book.

#### Customization
*   **TOML Configuration**: All settings are managed through a single `config.toml` file.
*   **Custom Processor Pipeline**: Users can define a sequence of pre-processors (acting on Markdown) and post-processors (acting on TeX) by providing their own Python scripts.
*   **Custom File Sorting**: The chapter order for book compilation can be controlled by a user-provided Python sorting script.

### Supported Callouts
```
>[!abstract] Definition
>[!note] Proposition
>[!note] Lemma
>[!note] Theorem
>[!question] Question
>[!question] Conjecture
>[!abstract] Axiom
>[!example] Example
>[!caution] Caution
>[!done] Alternative Proof
>[!note] Corollary
```

## Prerequisites

The following dependencies must be installed on your system before using `ofmc`. Note that the program is only tested on openSUSE Tumbleweed.

#### 1. System Tools
*   **Inkscape**: Required for converting SVG images.
    *   *Installation*: Use your system's package manager. For example, `pkexec zypper install inkscape`

#### 2. Python Environment
*   **Python 3.13+**
*   **uv**: Used for project and package management.
    *   *Installation*: See the official `uv` installation guide: [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv)

#### 3. LaTeX Distribution
*   A complete **XeLaTeX** distribution is required. **TeX Live** is recommended.
    *   *Installation*: This depends on your OS. For example: `pkexec zypper install texlive-scheme-full`.
    *   *Version Info*: `ofmc` is tested with TeX Live 2025 (`XeTeX 3.14...`).
*   **Required LaTeX Packages**: Ensure the following packages are installed, typically via your TeX distribution's package manager (e.g., `tlmgr install <package>`):
    ```
    fontspec, xeCJK, amsmath, amssymb, gensymb, mathrsfs, extpfeil, 
    graphicx, grffile, svg, hyperref, tcolorbox, upquote, xcolor, 
    soul, booktabs, tabularx, everypage, lastpage, refcount, titling
    ```

## Usage

Operations are controlled via the `ofmc` command. `uv run` automatically uses the `.venv` in the current project.

1.  **Create a configuration file:** Create a `config.toml` file. See the example below for all available options.

2.  **Run the compiler:**
    ```bash
    # Run using 'config.toml' in the current directory
    uv run ofmc

    # Specify a path to a different configuration file
    uv run ofmc -c /path/to/your/config.toml

    # View all command-line options
    uv run ofmc --help
    ```

Usage:
```
usage: ofmc [-h] [-c CONFIG_PATH] [-n]

Obsidian-Flavored Markdown to LaTeX Compiler.

options:
  -h, --help            show this help message and exit
  -c, --config CONFIG_PATH
                        Path to the configuration file (default: config.toml)
  -n, --no-logo         Disable Ascii Art logo.

```

## Configuration (`config.toml`)

Below is a full example of the `config.toml` file.

```toml
# --- Core Settings ---
# Absolute path to your Obsidian vault's root directory.
vault_root = "/home/felix/data/Notes/Notes Root"
# Directory where the final PDF(s) will be saved.
output_dir = "/home/felix/Desktop/Notes Exported"
# Author name to be included in the PDF metadata.
author = "Nuaptan F. Evalisk"

# --- Compilation Mode ---
# If true, compiles the entire vault. If false, compiles only the single file below.
batch_compile = true
# Path to a single markdown file to compile. Only used if batch_compile = false.
markdown_file = "/home/felix/Desktop/demo.md"

# --- File Filtering ---
# List of glob patterns for files/directories to exclude from compilation.
# Paths are relative to vault_root.
excluded = [ "Knowledge/**/*Homepage*.md", "Automatic Files/**" ]

# --- Document Structuring (for batch_compile = true) ---
# If true, assembles compiled files into a single PDF book.
enable_book_compile = true
book_title = "Some Title"
cover_image = "assets/logo.png" # Path relative to vault_root

# Defines the sections of the book and their order.
book_parts = [
    "Knowledge/Analysis",
    "Knowledge/Galois Theory",
    "Knowledge/Algebraic Topology",
    "Lecture Notes/Linear Algebra II",
]

# (Optional) Files to include at the beginning of the book.
front_matter = []	
# (Optional) Files to include at the end of the book.
back_matter = [ "Support Files/Book Titles.md" ]

# --- Customization ---
# Path to a custom Python script for sorting files within book_parts.
sorting_script = "metadata_sorter.py"

# --- Processor Pipeline ---
# Define custom pre-processing (Markdown -> Markdown) and post-processing (TeX -> TeX) steps.
# Lines starting with '$' are built-in processors.
# Other lines specify a custom script in the format "filename.py:function_name".
[processors]
post = [ 
	"$fix_align_environment", 
	"$replace_custom_arrow_tricks", 
	"$split_inline_display_math", 
	"$replace_tagged_dollars", 
	"$fix_mathbb_k", 
	"$fix_smaller_than", 
	"$fix_kern_syntax",
	"$replace_array_with_matrix_environments", 
	"$replace_bbox", 
	"$fix_choose", 
	"$fix_tcolorbox_label_tcolorbox", 
	"$remove_bad_tex_block_pointers" 
]
pre = [
	"custom_fixes.py:fix_markdown_spacing",
	"$preprocess_nested_blockquotes", 
	"$fix_callout_formulas", 
	"$insert_blank_blockquote_lines", 
	"$normalize_unicode"
]
```

## Screenshots
- Screenshot of a `.tex` file compiled from `.md` file. The editor is `Kile`.
[![Screenshot-20250822-161815.png](https://i.postimg.cc/KvrV7WQZ/Screenshot-20250822-161815.png)](https://postimg.cc/7fhmwmpc)

- Screenshot of a `.pdf` document compiled from the generated `.tex` file.
[![Screenshot-20250822-162156.png](https://i.postimg.cc/DwGSYqJy/Screenshot-20250822-162156.png)](https://postimg.cc/FY9FYkV2)

- Another `.pdf`, here you can see transclusions at work.
[![Screenshot-20250822-162408.png](https://i.postimg.cc/4Ngtk2GH/Screenshot-20250822-162408.png)](https://postimg.cc/5jsj836f)

- Screenshot of batch compilation in progress. The terminal is `Alacritty`.
[![Screenshot-20250822-162711.png](https://i.postimg.cc/v89qtKX4/Screenshot-20250822-162711.png)](https://postimg.cc/mhLyb8v4)
[![Screenshot-20250822-162803.png](https://i.postimg.cc/X7ShMWXK/Screenshot-20250822-162803.png)](https://postimg.cc/V5g4M3q5)

## License

`ofmc` is distributed under the GNU General Public License v3.0. See the `LICENSE` file for details.
