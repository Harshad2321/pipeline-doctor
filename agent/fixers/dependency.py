"""
Dependency error fixer - handles missing packages.
No AI API needed - directly modifies manifest files.
"""

import json
import os
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger


class DependencyFixer:
    """Fixes dependency errors by adding missing packages to manifest files."""

    def fix_dependency(self, error_info: dict, repo_path: str) -> dict:
        """
        Fix dependency error by adding package to appropriate manifest file.

        Args:
            error_info: Error information including package_name
            repo_path: Path to repository root

        Returns:
            Dict with fix_applied, file_modified, strategy
        """
        package_name = error_info.get("package_name")
        language = error_info.get("language", "unknown")

        if not package_name:
            logger.error("[DEPENDENCY FIXER] No package name found in error info")
            return {
                "success": False,
                "fix_applied": "No package name identified",
                "file_modified": None,
                "strategy": "dependency_fix_failed"
            }

        logger.info(f"[DEPENDENCY FIXER] Fixing missing {language} package: {package_name}")

        # Route to appropriate language handler
        if language == "python":
            return self._fix_python_dependency(package_name, repo_path)
        elif language == "node":
            return self._fix_node_dependency(package_name, repo_path)
        elif language == "go":
            return self._fix_go_dependency(package_name, repo_path)
        else:
            logger.warning(f"[DEPENDENCY FIXER] Unsupported language: {language}")
            print(
                f"\n[MANUAL ACTION REQUIRED] Dependency fix for language '{language}' "
                f"is not yet supported.\n"
                f"Please manually add '{package_name}' to your project dependencies.\n"
            )
            return {
                "success": False,
                "fix_applied": f"Unsupported language: {language}",
                "file_modified": None,
                "strategy": "dependency_fix_unsupported"
            }

    def _fix_python_dependency(self, package_name: str, repo_path: str) -> dict:
        """
        Fix Python dependency by adding to requirements.txt or pyproject.toml.

        Args:
            package_name: Python package name
            repo_path: Repository root path

        Returns:
            Fix result dict
        """
        # Check if package exists on PyPI
        if not self._verify_pypi_package(package_name):
            logger.warning(f"[DEPENDENCY FIXER] Package '{package_name}' not found on PyPI")
            print(
                f"\n[MANUAL ACTION REQUIRED] Package '{package_name}' not found on PyPI.\n"
                f"This might be a typo or a private package.\n"
                f"Please verify the package name manually.\n"
            )
            # Continue anyway - might be a subpackage or local package

        # Try requirements.txt first
        requirements_path = os.path.join(repo_path, "requirements.txt")
        if os.path.exists(requirements_path):
            return self._add_to_requirements_txt(package_name, requirements_path)

        # Try pyproject.toml
        pyproject_path = os.path.join(repo_path, "pyproject.toml")
        if os.path.exists(pyproject_path):
            return self._add_to_pyproject_toml(package_name, pyproject_path)

        # No manifest file found
        logger.error(f"[DEPENDENCY FIXER] No Python manifest file found in {repo_path}")
        print(
            f"\n[MANUAL ACTION REQUIRED] No requirements.txt or pyproject.toml found.\n"
            f"Please create requirements.txt in {repo_path} and add:\n"
            f"  {package_name}\n"
            f"Then re-run the agent.\n"
        )
        return {
            "success": False,
            "fix_applied": "No manifest file found",
            "file_modified": None,
            "strategy": "dependency_fix_failed"
        }

    def _add_to_requirements_txt(self, package_name: str, file_path: str) -> dict:
        """Add package to requirements.txt."""
        try:
            # Read existing content
            with open(file_path, 'r') as f:
                content = f.read()

            # Check if package already exists
            lines = content.split('\n')
            for line in lines:
                if line.strip().startswith(package_name):
                    logger.info(f"[DEPENDENCY FIXER] Package {package_name} already in requirements.txt")
                    return {
                        "success": True,
                        "fix_applied": f"Package {package_name} already present",
                        "file_modified": file_path,
                        "strategy": "dependency_already_present"
                    }

            # Add package
            if not content.endswith('\n'):
                content += '\n'
            content += f"{package_name}\n"

            # Write back
            with open(file_path, 'w') as f:
                f.write(content)

            logger.info(f"[DEPENDENCY FIXER] Added {package_name} to requirements.txt")
            return {
                "success": True,
                "fix_applied": f"Added {package_name} to requirements.txt",
                "file_modified": file_path,
                "strategy": "manifest_append"
            }

        except Exception as e:
            logger.error(f"[DEPENDENCY FIXER] Failed to modify requirements.txt: {e}")
            return {
                "success": False,
                "fix_applied": f"Error modifying file: {e}",
                "file_modified": None,
                "strategy": "dependency_fix_failed"
            }

    def _add_to_pyproject_toml(self, package_name: str, file_path: str) -> dict:
        """Add package to pyproject.toml dependencies."""
        logger.warning("[DEPENDENCY FIXER] pyproject.toml auto-fix not fully implemented")
        print(
            f"\n[MANUAL ACTION REQUIRED] Please add '{package_name}' to "
            f"{file_path} dependencies section manually.\n"
        )
        return {
            "success": False,
            "fix_applied": "pyproject.toml modification requires manual action",
            "file_modified": None,
            "strategy": "dependency_fix_manual"
        }

    def _fix_node_dependency(self, package_name: str, repo_path: str) -> dict:
        """Fix Node.js dependency by adding to package.json."""
        package_json_path = os.path.join(repo_path, "package.json")

        if not os.path.exists(package_json_path):
            logger.error(f"[DEPENDENCY FIXER] No package.json found in {repo_path}")
            print(
                f"\n[MANUAL ACTION REQUIRED] No package.json found.\n"
                f"Please create package.json in {repo_path} and run:\n"
                f"  npm install {package_name}\n"
            )
            return {
                "success": False,
                "fix_applied": "No package.json found",
                "file_modified": None,
                "strategy": "dependency_fix_failed"
            }

        try:
            # Read package.json
            with open(package_json_path, 'r') as f:
                package_data = json.load(f)

            # Add to dependencies
            if "dependencies" not in package_data:
                package_data["dependencies"] = {}

            if package_name in package_data.get("dependencies", {}):
                logger.info(f"[DEPENDENCY FIXER] Package {package_name} already in package.json")
                return {
                    "success": True,
                    "fix_applied": f"Package {package_name} already present",
                    "file_modified": package_json_path,
                    "strategy": "dependency_already_present"
                }

            package_data["dependencies"][package_name] = "latest"

            # Write back
            with open(package_json_path, 'w') as f:
                json.dump(package_data, f, indent=2)

            logger.info(f"[DEPENDENCY FIXER] Added {package_name} to package.json")
            return {
                "success": True,
                "fix_applied": f"Added {package_name} to package.json",
                "file_modified": package_json_path,
                "strategy": "manifest_append"
            }

        except Exception as e:
            logger.error(f"[DEPENDENCY FIXER] Failed to modify package.json: {e}")
            return {
                "success": False,
                "fix_applied": f"Error modifying file: {e}",
                "file_modified": None,
                "strategy": "dependency_fix_failed"
            }

    def _fix_go_dependency(self, package_name: str, repo_path: str) -> dict:
        """Fix Go dependency (requires go get command)."""
        logger.warning("[DEPENDENCY FIXER] Go dependency auto-fix requires go commands")
        print(
            f"\n[MANUAL ACTION REQUIRED] Please run the following command:\n"
            f"  cd {repo_path}\n"
            f"  go get {package_name}\n"
        )
        return {
            "success": False,
            "fix_applied": "Go dependency requires manual go get",
            "file_modified": None,
            "strategy": "dependency_fix_manual"
        }

    def _verify_pypi_package(self, package_name: str) -> bool:
        """
        Verify that a package exists on PyPI.

        Args:
            package_name: Package to check

        Returns:
            True if package exists, False otherwise
        """
        try:
            url = f"https://pypi.org/pypi/{package_name}/json"
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                return response.status_code == 200
        except Exception:
            return False
