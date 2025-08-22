# ofmc/locator.py

from pathlib import Path
from collections import deque


class Locator:
    def __init__(self, vault_root: Path, current_file: Path):
        if not vault_root.is_dir():
            raise ValueError("Vault root must be an existing directory.")
        self.vault_root = vault_root.resolve()
        self.current_file = current_file.resolve()

    def _bfs_search(self, start_dir: Path, target_filename: str) -> Path | None:
        """
        Performs a Breadth-First Search for a file starting from a directory.

        Args:
            start_dir: The directory to start the search from.
            target_filename: The name of the file to find (e.g., "1.png").

        Returns:
            The absolute Path to the first match found, or None if not found.
        """
        queue = deque([start_dir])
        visited = {start_dir}

        while queue:
            current_dir = queue.popleft()

            # Check if the file exists in the current directory
            potential_path = current_dir / target_filename
            if potential_path.is_file():
                return potential_path

            # Add subdirectories to the queue for the next level of search
            try:
                for entry in current_dir.iterdir():
                    if entry.is_dir() and entry not in visited:
                        visited.add(entry)
                        queue.append(entry)
            except PermissionError:
                # Ignore directories we can't read
                continue

        return None

    def resolve(self, link_target: str) -> str | None:
        """
        Resolves a wikilink target name to an absolute file path.

        The search order is:
        1. If link_target contains slashes, treat it as a relative path from the vault root.
        2. Perform a BFS search starting from the current file's directory ("downwards").
        3. If not found, perform a vault-wide BFS search from the vault root ("upwards/sideways").

        Args:
            link_target: The filename from the wikilink, e.g., "1.png".

        Returns:
            A string containing the absolute path, or None if not found.
        """
        target_path = Path(link_target)

        # --- Rule 1: Explicit path from vault root ---
        # If link_target is "assets/1.png", this rule will trigger.
        if len(target_path.parts) > 1:
            full_path = self.vault_root / target_path
            if full_path.is_file():
                return str(full_path)

        # --- Rule 2: BFS search from current file's directory (local & downwards) ---
        # This will find the closest match in or below the current folder.
        # For test.md in /folder, this searches /folder, then /folder/assets, etc.
        local_search_start_dir = self.current_file.parent
        found_path = self._bfs_search(local_search_start_dir, target_path.name)
        if found_path:
            return str(found_path)

        # --- Rule 3: Vault-wide BFS search if local search fails ---
        # This handles finding files "above" or in sibling directories.
        # For test.md, this will search the entire vault from the top.
        # It's crucial to avoid re-searching if the local dir IS the vault root.
        if local_search_start_dir != self.vault_root:
            found_path = self._bfs_search(self.vault_root, target_path.name)
            if found_path:
                return str(found_path)

        # If all searches fail, return None
        return None
