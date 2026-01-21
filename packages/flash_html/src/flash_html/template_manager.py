"""
Core Template Engine for Flash HTML.

This module implements the `TemplateManager`, a robust wrapper around Jinja2
designed for modern modular web applications. It solves the problem of
distributing templates across multiple packages (e.g., Auth, Admin, Core)
while allowing the main application to override them easily.

Usage Lifecycle:
    1.  **Instantiation:** The manager is created during the application startup
        phase (e.g., FastAPI lifespan). It immediately scans the filesystem.
    2.  **Access:** The configured `Jinja2Templates` instance is accessed via
        the `.templates` attribute.
    3.  **Rendering:** Views use `.templates.TemplateResponse(...)` to return HTML.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Sequence

from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

# Standard directories to ignore during recursive scanning.
# These match standard Python/Node/Git conventions to prevent
# accidental loading of system or dependency templates.
_SKIP_DIRECTORIES = frozenset(
    {
        ".venv",
        "venv",
        "env",
        "site-packages",
        "__pycache__",
        "node_modules",
        ".git",
        ".tox",
        ".pytest_cache",
        ".idea",
        ".vscode",
    }
)


class TemplateManager:
    """
    Manages Jinja2 template loading, discovery, and context injection.

    Unlike a standard Jinja2 setup where paths are hardcoded, this manager
    implements a "Discovery Strategy" similar to Django's `APP_DIRS`.

    **Discovery Algorithm:**
    1.  **Project Root Templates:** Checks `project_root/templates`. If exists,
        it gets highest priority.
    2.  **Explicit Directories:** Paths passed via `extra_directories`
        (e.g., from `flash_admin`).
    3.  **Recursive Discovery:** Scans subdirectories of `project_root` for
        any folder named `templates`, skipping virtual environments.
    4.  **Internal Templates:** Defaults provided by `flash_html` itself.

    Attributes:
        templates (Jinja2Templates): The fully configured Jinja2 environment,
            ready to render responses.
    """

    def __init__(
        self,
        project_root: Path | str | None = None,
        extra_directories: Sequence[Path | str] | None = None,
        global_context: dict[str, Any] | None = None,
        global_functions: dict[str, Callable] | None = None,
    ):
        """
        Initialize the TemplateManager and load all templates immediately.

        Args:
            project_root (Path | str | None): The root directory of the user's
                application. If provided, the manager will recursively scan this
                path for 'templates' folders.

            extra_directories (Sequence[Path | str] | None): A list of absolute
                paths to register manually. Use this to integrate templates
                from other installed packages (e.g., `flash_admin`, `flash_auth`).

            global_context (dict[str, Any] | None): A dictionary of variables
                to inject into *every* template (e.g., `{"site_name": "My App"}`).

            global_functions (dict[str, Callable] | None): A dictionary of
                functions to make available in *every* template
                (e.g., `{"static": static_url_builder}`).

        Example:
            >>> from pathlib import Path
            >>> # 1. Define global helpers
            >>> def current_year(): return 2024
            >>>
            >>> # 2. Initialize Manager
            >>> manager = TemplateManager(
            ...     project_root=Path("/app"),
            ...     global_context={"app_name": "Flash"},
            ...     global_functions={"year": current_year}
            ... )
            >>>
            >>> # 3. Use it in a View
            >>> # return manager.templates.TemplateResponse("index.html", {"request": req})
        """
        self._directories: list[str] = []

        # --- Step 1: Register Internal Templates ---
        # These act as the fallback for base components.
        # We always register this path, even if it doesn't exist yet, to ensure
        # the list passed to Jinja2Templates is never empty (which causes a crash).
        internal_templates = Path(__file__).parent / "templates"
        self._add_directory(internal_templates)

        # --- Step 2: Register Explicit External Directories ---
        # Useful for integrating other packages in the Flash ecosystem.
        if extra_directories:
            for d in extra_directories:
                self._add_directory(d)

        # --- Step 3: Scan Project for 'templates' folders ---
        # This provides the "Django-like" convenience.
        if project_root:
            self._scan_project_directories(Path(project_root))

        logger.debug(f"HTML Engine initialized with directories: {self._directories}")

        # --- Step 4: Create the Jinja2 Environment ---
        # We pass the collected list of strings to Starlette/FastAPI's wrapper.
        # Note: Starlette requires `directory` to be a non-empty list if env is None.
        self.templates = Jinja2Templates(directory=self._directories)

        # --- Step 5: Inject Globals ---
        # These are now available in {{ variable }} or {{ function() }}
        if global_context:
            for name, value in global_context.items():
                self.templates.env.globals[name] = value

        if global_functions:
            for name, func in global_functions.items():
                self.templates.env.globals[name] = func

    def _add_directory(self, path: Path | str) -> None:
        """
        Register a new template directory.

        Internal helper to ensure paths are converted to strings and
        duplicates are avoided. Uses absolute paths to prevent issues with
        relative paths (./templates vs /app/templates).
        """
        # Resolve to absolute path to handle ../ or ./ correctly across OSs
        # Path.resolve() handles symlinks and absolute conversions.
        path_obj = Path(path).resolve()
        path_str = str(path_obj)

        if path_str not in self._directories:
            self._directories.append(path_str)

    def _scan_project_directories(self, root: Path) -> None:
        """
        Recursively find and register 'templates' folders.

        Logic:
        1. Checks root/templates (Highest Priority).
        2. Walks the tree looking for other 'templates' dirs.
        3. Skips system directories defined in _SKIP_DIRECTORIES.
        """
        root = root.resolve()

        # Priority 1: Project Root 'templates' folder
        # We insert at 0 to ensure user overrides take precedence over everything else.
        root_tpl = root / "templates"
        if root_tpl.is_dir():
            root_tpl_str = str(root_tpl)
            if root_tpl_str not in self._directories:
                self._directories.insert(0, root_tpl_str)
            else:
                # If it was already added (e.g. via extra_directories), move it to front
                self._directories.remove(root_tpl_str)
                self._directories.insert(0, root_tpl_str)

        # Priority 2: Recursively found app directories
        for path in root.rglob("templates"):
            if not path.is_dir():
                continue

            # Optimization: Skip system/venv folders
            parts = {p.lower() for p in path.parts}
            if not parts.isdisjoint(_SKIP_DIRECTORIES):
                continue

            # Avoid adding the root folder twice
            if str(path) == str(root_tpl):
                continue

            self._add_directory(path)


__all__ = ["TemplateManager"]
