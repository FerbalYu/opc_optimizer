"""Plugin system for OPC Local Optimizer.

Defines the BaseNode interface and plugin loading utilities.
Users can create custom nodes (e.g. lint_node, security_scan_node)
and register them via opc.config.yaml.
"""

import os
import logging
import importlib.util
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

logger = logging.getLogger("opc.plugins")

# Plugin cache for hot reload
_plugin_cache: Dict[str, List[BaseNode]] = {}


class BaseNode(ABC):
    """Abstract base class for custom OPC nodes.

    To create a custom node:
    1. Create a Python file in your project's `opc_plugins/` directory
    2. Define a class that inherits from BaseNode
    3. Implement the `run()` method
    4. Register it in opc.config.yaml under `plugins`

    Example:
        class LintNode(BaseNode):
            name = "lint"

            def run(self, state: dict) -> dict:
                # Run linting, update state
                state["lint_results"] = "All clean"
                return state
    """

    name: str = ""  # Must be set by subclass
    description: str = ""
    insert_after: str = "test"  # Which built-in node this runs after

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the node logic and return the updated state.

        Args:
            state: The OptimizerState dict

        Returns:
            The updated state dict
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


def _validate_plugin(plugin: BaseNode) -> bool:
    """Validate that a plugin has all required attributes.

    Args:
        plugin: The plugin instance to validate

    Returns:
        True if valid, False otherwise
    """
    required_attrs = ["name", "run"]
    has_all = all(hasattr(plugin, attr) for attr in required_attrs)
    if not has_all:
        logger.warning(
            f"Plugin {plugin.__class__.__name__} is missing required attributes"
        )
        return False

    if not plugin.name:
        logger.warning(f"Plugin {plugin.__class__.__name__} has empty name")
        return False

    return True


def load_plugins(plugin_dir: str, use_cache: bool = True) -> List[BaseNode]:
    """Load all plugin node classes from a directory.

    Scans `plugin_dir` for .py files, imports them, and finds all
    BaseNode subclasses.

    Args:
        plugin_dir: Absolute path to the plugins directory
        use_cache: If True, return cached plugins if available

    Returns:
        List of instantiated BaseNode subclasses
    """
    if use_cache and plugin_dir in _plugin_cache:
        return _plugin_cache[plugin_dir]

    if not os.path.isdir(plugin_dir):
        return []

    plugins = []
    for filename in sorted(os.listdir(plugin_dir)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue

        filepath = os.path.join(plugin_dir, filename)
        module_name = f"opc_plugin_{filename[:-3]}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find all BaseNode subclasses in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseNode)
                    and attr is not BaseNode
                    and attr.name
                ):
                    instance = attr()
                    if _validate_plugin(instance):
                        plugins.append(instance)
                        logger.info(f"Loaded plugin: {instance}")
                    else:
                        logger.warning(
                            f"Plugin {attr_name} validation failed, skipping"
                        )

        except Exception as e:
            logger.error(f"Failed to load plugin {filename}: {e}")

    _plugin_cache[plugin_dir] = plugins
    return plugins


def discover_plugins(project_path: str, use_cache: bool = True) -> List[BaseNode]:
    """Discover plugins from the project's opc_plugins/ directory.

    Args:
        project_path: The project root path
        use_cache: If True, use cached plugins

    Returns:
        List of instantiated plugin nodes
    """
    plugin_dir = os.path.join(project_path, "opc_plugins")
    plugins = load_plugins(plugin_dir, use_cache=use_cache)
    if plugins:
        logger.info(f"Discovered {len(plugins)} plugin(s) from {plugin_dir}")
    return plugins


def reload_plugins(project_path: str) -> List[BaseNode]:
    """Reload plugins from disk, clearing the cache.

    Args:
        project_path: The project root path

    Returns:
        List of reloaded plugin nodes
    """
    plugin_dir = os.path.join(project_path, "opc_plugins")
    if plugin_dir in _plugin_cache:
        del _plugin_cache[plugin_dir]
    logger.info(f"Plugin cache cleared for {plugin_dir}")
    return discover_plugins(project_path, use_cache=False)


def clear_plugin_cache() -> None:
    """Clear all cached plugins."""
    global _plugin_cache
    _plugin_cache.clear()
    logger.debug("All plugin caches cleared")
