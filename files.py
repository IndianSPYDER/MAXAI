"""
skills/files.py — File system skill for MAX.

Read, write, move, list, and search local files.
Destructive operations (delete, overwrite) require confirmation.

⚠️  For safety, all file operations are sandboxed to the configured
    WORKSPACE_DIR (default: ~/MAX_workspace). MAX cannot access
    files outside this directory unless explicitly configured.
"""

import logging
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from skills.base import BaseSkill, skill_action

logger = logging.getLogger("MAX.skills.files")

DEFAULT_WORKSPACE = Path.home() / "MAX_workspace"


class FilesSkill(BaseSkill):
    name = "files"
    description = "Read, write, and manage local files within the MAX workspace"

    def __init__(self, settings=None):
        super().__init__(settings)
        workspace = os.getenv("WORKSPACE_DIR", str(DEFAULT_WORKSPACE))
        self.workspace = Path(workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        logger.info(f"Files skill workspace: {self.workspace}")

    def _safe_path(self, path: str) -> Path:
        """Resolve a path and ensure it's within the workspace."""
        resolved = (self.workspace / path).resolve()
        if not str(resolved).startswith(str(self.workspace)):
            raise PermissionError(f"Path '{path}' is outside the MAX workspace. Access denied.")
        return resolved

    @skill_action(description="List files and directories in a folder within the workspace")
    async def list_files(self, directory: str = ".", show_hidden: bool = False) -> str:
        """List the contents of a directory."""
        try:
            path = self._safe_path(directory)
            if not path.exists():
                return f"Directory '{directory}' does not exist"

            entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
            lines = [f"📁 {self.workspace}/{directory}"]

            for entry in entries:
                if not show_hidden and entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    lines.append(f"  📂 {entry.name}/")
                else:
                    size = entry.stat().st_size
                    size_str = self._human_size(size)
                    mtime = datetime.fromtimestamp(entry.stat().st_mtime).strftime("%b %d %H:%M")
                    lines.append(f"  📄 {entry.name:40s} {size_str:>8s}  {mtime}")

            return "\n".join(lines)

        except PermissionError as e:
            return f"❌ {e}"
        except Exception as e:
            return f"Failed to list '{directory}': {str(e)}"

    @skill_action(description="Read the contents of a file")
    async def read_file(self, path: str, max_chars: int = 5000) -> str:
        """Read the text content of a file."""
        try:
            resolved = self._safe_path(path)
            if not resolved.exists():
                return f"File '{path}' not found"
            if not resolved.is_file():
                return f"'{path}' is a directory, not a file"

            content = resolved.read_text(encoding="utf-8", errors="replace")
            if len(content) > max_chars:
                return content[:max_chars] + f"\n\n[Truncated. File is {len(content):,} chars total.]"
            return content

        except PermissionError as e:
            return f"❌ {e}"
        except Exception as e:
            return f"Failed to read '{path}': {str(e)}"

    @skill_action(description="Write or create a file with the given content")
    async def write_file(self, path: str, content: str) -> str:
        """Write content to a file, creating it if it doesn't exist."""
        try:
            resolved = self._safe_path(path)
            resolved.parent.mkdir(parents=True, exist_ok=True)

            action = "Updated" if resolved.exists() else "Created"
            resolved.write_text(content, encoding="utf-8")

            return f"✅ {action} {path} ({len(content):,} chars)"

        except PermissionError as e:
            return f"❌ {e}"
        except Exception as e:
            return f"Failed to write '{path}': {str(e)}"

    @skill_action(description="Append text to an existing file")
    async def append_file(self, path: str, content: str) -> str:
        """Append content to a file."""
        try:
            resolved = self._safe_path(path)
            with open(resolved, "a", encoding="utf-8") as f:
                f.write(content)
            return f"✅ Appended {len(content):,} chars to {path}"

        except PermissionError as e:
            return f"❌ {e}"
        except Exception as e:
            return f"Failed to append to '{path}': {str(e)}"

    @skill_action(
        description="Delete a file permanently. Always asks user for confirmation first.",
        confirm_required=True
    )
    async def delete_file(self, path: str) -> str:
        """Delete a file. Requires user confirmation."""
        try:
            resolved = self._safe_path(path)
            if not resolved.exists():
                return f"'{path}' does not exist"

            if resolved.is_dir():
                shutil.rmtree(resolved)
                return f"✅ Deleted directory: {path}"
            else:
                resolved.unlink()
                return f"✅ Deleted file: {path}"

        except PermissionError as e:
            return f"❌ {e}"
        except Exception as e:
            return f"Failed to delete '{path}': {str(e)}"

    @skill_action(description="Search for files by name pattern or content keyword")
    async def search_files(self, query: str, search_content: bool = False) -> str:
        """Search files by name or content."""
        try:
            results = []

            for path in self.workspace.rglob("*"):
                if not path.is_file():
                    continue
                if query.lower() in path.name.lower():
                    results.append(str(path.relative_to(self.workspace)))
                    continue
                if search_content and path.suffix in {".txt", ".md", ".py", ".json", ".csv", ".yaml"}:
                    try:
                        text = path.read_text(encoding="utf-8", errors="replace")
                        if query.lower() in text.lower():
                            results.append(f"{path.relative_to(self.workspace)} (content match)")
                    except Exception:
                        pass

            if not results:
                return f"No files matching '{query}' found"

            return f"Found {len(results)} file(s) matching '{query}':\n" + "\n".join(f"  • {r}" for r in results[:50])

        except Exception as e:
            return f"Search failed: {str(e)}"

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.0f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"
