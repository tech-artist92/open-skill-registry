import unittest
from pathlib import Path
import tomllib


class TestProjectSetup(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path(__file__).resolve().parent.parent.parent
        self.pyproject_path = self.root_dir / "pyproject.toml"

    def test_pyproject_toml_exists_and_is_valid(self):
        self.assertTrue(
            self.pyproject_path.is_file(),
            f"pyproject.toml does not exist at {self.pyproject_path}",
        )
        content = self.pyproject_path.read_text(encoding="utf-8")
        parsed = tomllib.loads(content)
        self.assertIn("project", parsed)

    def test_project_metadata(self):
        content = self.pyproject_path.read_text(encoding="utf-8")
        parsed = tomllib.loads(content)
        project = parsed["project"]
        self.assertEqual(project.get("name"), "open-skill-registry")
        self.assertIn("version", project)
        self.assertTrue(project.get("requires-python", "").startswith(">=3.11"))

    def test_required_dependencies(self):
        content = self.pyproject_path.read_text(encoding="utf-8")
        parsed = tomllib.loads(content)
        project = parsed.get("project", {})
        dependencies = project.get("dependencies", [])

        expected_dependencies = [
            "fastapi",
            "uvicorn",
            "sqlmodel",
            "sqlalchemy[asyncio]",
            "asyncpg",
            "aiosqlite>=0.20.0",
            "pgvector",
            "fastembed>=0.3.0",
            "numpy>=1.24.0",
            "pyyaml>=6.0.1",
            "redis",
            "typer",
            "rich",
            "httpx",
            "pydantic>=2.8.0",
        ]

        # Ensure all expected dependencies or their version constraints are in dependencies list
        dep_str = " ".join(dependencies)
        for dep in expected_dependencies:
            # Check either exact match or package name match
            pkg_name = dep.split(">=")[0].split("[")[0]
            self.assertTrue(
                any(pkg_name in item for item in dependencies),
                f"Missing dependency: {dep} in {dependencies}",
            )

    def test_optional_dependencies_extras(self):
        content = self.pyproject_path.read_text(encoding="utf-8")
        parsed = tomllib.loads(content)
        project = parsed.get("project", {})
        optional_deps = project.get("optional-dependencies", {})

        self.assertIn("cli", optional_deps)
        self.assertIn("server", optional_deps)
        self.assertIn("all", optional_deps)

    def test_standard_directories_exist(self):
        expected_dirs = [
            self.root_dir / "src" / "open_skill_registry",
            self.root_dir / "tests" / "unit",
            self.root_dir / "tests" / "integration",
            self.root_dir / "tests" / "contract",
            self.root_dir / "tests" / "adk",
        ]

        for directory in expected_dirs:
            self.assertTrue(
                directory.is_dir(),
                f"Required directory does not exist: {directory}",
            )

    def test_src_open_skill_registry_init_exists(self):
        init_file = self.root_dir / "src" / "open_skill_registry" / "__init__.py"
        self.assertTrue(
            init_file.is_file(),
            f"src/open_skill_registry/__init__.py does not exist at {init_file}",
        )


if __name__ == "__main__":
    unittest.main()
