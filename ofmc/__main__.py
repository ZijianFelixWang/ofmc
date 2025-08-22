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

# ofmc/__main__.py

"""
Makes the 'ofmc' package runnable with 'python -m ofmc'.
"""
from .main import main

if __name__ == "__main__":
    main()
