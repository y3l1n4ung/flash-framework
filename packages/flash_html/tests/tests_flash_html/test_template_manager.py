import os
from pathlib import Path
from flash_html.template_manager import TemplateManager


class TestTemplateManager:
    def test_initialization_defaults(self):
        """
        Requirement: Manager initializes safely with no arguments.
        """
        manager = TemplateManager()
        assert manager.templates is not None
        # Should contain at least the internal templates path
        assert len(manager.templates.env.loader.searchpath) > 0

    def test_internal_template_loading(self):
        """
        Requirement: The manager must always load the internal 'templates' directory.
        """
        manager = TemplateManager()

        expected_suffix = os.path.join("flash_html", "templates")

        loader_paths = manager.templates.env.loader.searchpath
        assert any(str(p).endswith(expected_suffix) for p in loader_paths)

    def test_global_injection(self):
        """
        Requirement: Context and Functions must be injected into the environment.
        """

        def my_func():
            return "works"

        manager = TemplateManager(
            global_context={"site": "Flash"}, global_functions={"check": my_func}
        )

        assert manager.templates.env.globals["site"] == "Flash"
        assert manager.templates.env.globals["check"]() == "works"

    def test_directory_scanning_priority(self, tmp_path):
        """
        Requirement:
        1. Project Root `templates/` (Highest)
        2. App-level `templates/` (e.g., `app/feature/templates`)
        """
        # --- Setup Mock Filesystem ---
        # 1. Root templates
        root_tpl = tmp_path / "templates"
        root_tpl.mkdir()

        # 2. App templates
        app_tpl = tmp_path / "my_app" / "templates"
        app_tpl.mkdir(parents=True)

        # --- Run ---
        manager = TemplateManager(project_root=tmp_path)
        loader_paths = manager.templates.env.loader.searchpath

        # --- Assertions ---
        # Convert all to strings for comparison
        root_str = str(root_tpl.resolve())
        app_str = str(app_tpl.resolve())

        assert root_str in loader_paths
        assert app_str in loader_paths

        # Find indices to check priority
        root_index = loader_paths.index(root_str)
        app_index = loader_paths.index(app_str)

        # Lower index = Higher priority in Jinja2
        assert root_index < app_index

    def test_deeply_nested_templates(self, tmp_path):
        """
        Requirement: Recursive scanning works for deep nesting.
        """
        nested = tmp_path / "a" / "b" / "c" / "d" / "templates"
        nested.mkdir(parents=True)

        manager = TemplateManager(project_root=tmp_path)
        loader_paths = manager.templates.env.loader.searchpath

        assert str(nested.resolve()) in loader_paths

    def test_skip_directories_cross_platform(self, tmp_path):
        """
        Requirement:
        Should skip directories in _SKIP_DIRECTORIES (e.g., .venv, node_modules).
        Must be CASE-INSENSITIVE for Windows compatibility (Node_Modules should be skipped).
        """
        # 1. Standard .venv
        venv_tpl = tmp_path / ".venv" / "templates"
        venv_tpl.mkdir(parents=True)

        # 2. Case-varied directory (common on Windows/User typos)
        # "Node_Modules" vs "node_modules"
        node_tpl = tmp_path / "Node_Modules" / "templates"
        node_tpl.mkdir(parents=True)

        # 3. Valid directory
        valid_tpl = tmp_path / "features" / "templates"
        valid_tpl.mkdir(parents=True)

        manager = TemplateManager(project_root=tmp_path)
        loader_paths = manager.templates.env.loader.searchpath

        # Should contain valid
        assert str(valid_tpl.resolve()) in loader_paths

        # Should NOT contain ignored
        # Note: We iterate because resolve() might behave differently depending on OS existence
        # but these dirs exist in tmp_path.
        assert str(venv_tpl.resolve()) not in loader_paths
        assert str(node_tpl.resolve()) not in loader_paths

    def test_deduplication_and_resolution(self, tmp_path):
        """
        Requirement:
        Paths should be resolved to absolute to prevent duplicates
        (e.g., adding '.' and '/absolute/path/to/.' should result in one entry).
        Also verifies priority logic when a scanned path is also added manually.
        """
        root_tpl = tmp_path / "templates"
        root_tpl.mkdir()

        # Pass the same directory twice: once via scanning, once via extra_directories
        manager = TemplateManager(
            project_root=tmp_path,
            extra_directories=[root_tpl],  # Pass Path object directly
        )

        loader_paths = manager.templates.env.loader.searchpath

        # Count occurrences of the root template path
        resolved_path = str(root_tpl.resolve())
        count = loader_paths.count(resolved_path)

        assert count == 1, (
            f"Path {resolved_path} should appear exactly once, found {count}"
        )

        # Root template should be at index 0 (Highest priority) due to scanning logic logic
        assert loader_paths[0] == resolved_path

    def test_non_existent_project_root_handled_gracefully(self):
        """
        Requirement: Should handle non-existent root gracefully without crashing.
        The manager should just log/ignore it and continue with internal templates.
        """
        manager = TemplateManager(project_root=Path("non_existent_path_xyz_123"))

        # Should still initialize successfully
        assert manager.templates is not None

        # Should still contain the internal templates path
        expected_suffix = os.path.join("flash_html", "templates")
        loader_paths = manager.templates.env.loader.searchpath
        assert any(str(p).endswith(expected_suffix) for p in loader_paths)

    def test_rendering_functional(self, tmp_path):
        """
        Requirement: The engine can actually render an HTML file found in scanned paths.
        This verifies the integration with Jinja2Templates.
        """
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        (tpl_dir / "hello.html").write_text("Hello {{ name }}", encoding="utf-8")

        manager = TemplateManager(project_root=tmp_path)

        # Test rendering via the exposed Jinja2Templates instance
        template = manager.templates.get_template("hello.html")
        rendered = template.render(name="Developer")

        assert rendered == "Hello Developer"

    def test_scan_ignores_files_named_templates(self, tmp_path):
        """
        Requirement: The scanner should ignore files named 'templates' (if not path.is_dir()),
        it should only register directories.
        """
        # Create a file named 'templates' instead of a directory
        # Structure: /tmp/app/templates (file)
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        bad_file = app_dir / "templates"
        bad_file.touch()

        manager = TemplateManager(project_root=tmp_path)
        loader_paths = manager.templates.env.loader.searchpath

        # Verify the file path is NOT in the loader paths
        # We verify that the 'app/templates' path was skipped
        bad_path_str = str(bad_file.resolve())
        assert bad_path_str not in loader_paths
