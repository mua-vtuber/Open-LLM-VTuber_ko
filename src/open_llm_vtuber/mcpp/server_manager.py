"""MCP Server Manager for Open-LLM-Vtuber."""

import shutil
import sys
import json
import importlib.util

from pathlib import Path
from typing import Dict, Optional, Union, Any
from loguru import logger

from .types import MCPServer, MCPServerType
from .utils.path import validate_file

DEFAULT_CONFIG_PATH = Path(__file__).parent / "configs" / "mcp_servers.json"


class MCPServerManager:
    """MCP Server Manager for managing server files."""

    def __init__(self, config_path: str | Path = DEFAULT_CONFIG_PATH) -> None:
        """Initialize the MCP Server Manager."""
        try:
            config_path = validate_file(config_path, ".json")
        except ValueError:
            logger.error(f"MCPSM: File '{config_path}' does not exist, or is not a json file.")
            raise ValueError(f"MCPSM: File '{config_path}' does not exist, or is not a json file.")

        self.config: Dict[str, Union[str, dict]] = json.loads(
            config_path.read_text(encoding="utf-8")
        )

        self.servers: Dict[str, MCPServer] = {}

        self.npx_available = self._detect_runtime("npx")
        self.uvx_available = self._detect_runtime("uvx")
        self.node_available = self._detect_runtime("node")

        self.search_custom_servers()
        self.load_official_servers()

    def _detect_runtime(self, target: str) -> bool:
        """Check if a runtime is available in the system PATH."""
        founded = shutil.which(target)
        return True if founded else False

    def search_custom_servers(self) -> None:
        """Search for available mcp servers in the custom directory."""
        custom_servers_path = Path(self.config["custom_servers_path"])
        if not custom_servers_path.is_absolute():
            custom_servers_path = Path(__file__).parent / custom_servers_path
        custom_servers_path = custom_servers_path.absolute()

        if not custom_servers_path.exists() or not custom_servers_path.is_dir():
            logger.error(f"MCPSM: Path '{custom_servers_path}' does not exist, or is not a directory.")
            raise ValueError(
                f"MCPSM: Path '{custom_servers_path}' does not exist, or is not a directory."
                "Please check your configuration file."
            )

        for path in custom_servers_path.iterdir():
            if path.suffix == ".py":
                server_name = path.stem

                spec = importlib.util.spec_from_file_location(server_name, path)
                if spec is None or spec.loader is None:
                    logger.warning(f"MCPSM: Failed to load module from '{path}'. Ignoring.")
                    continue

                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                    env = getattr(module, "__envs__", None)
                    timeout = getattr(module, "__timeout__", None)

                    self.servers[server_name] = MCPServer(
                        name=server_name,
                        command=sys.executable,
                        args=[str(path)],
                        env=env,
                        timeout=timeout,
                        type=MCPServerType.Custom,
                        path=path,
                    )
                    logger.debug(f"MCPSM: Found custom server: '{server_name}.py'")
                except Exception as e:
                    logger.warning(f"MCPSM: Error loading module '{server_name}': {e}. Ignoring.")
                    continue

            elif path.suffix == ".js":
                server_name = path.stem
                if not self.npx_available:
                    logger.warning(f"Found TypeScript server '{server_name}.js' but node is not available.")
                    continue
                self.servers[server_name] = MCPServer(
                    name=server_name,
                    command="node",
                    args=[str(path)],
                    type=MCPServerType.Custom,
                    path=path,
                )
                logger.debug(f"MCPSM: Found custom server: '{server_name}.js'")
            else:
                continue

    def load_official_servers(self) -> None:
        """Load official servers from the config file."""
        officials: Dict[str, Dict[str, Any]] = self.config.get("officials", {})
        if officials == {}:
            logger.warning("MCPSM: No official servers found in the config file.")
            return

        for server_name, server_details in officials.items():
            if "command" not in server_details or "args" not in server_details:
                logger.warning(f"MCPSM: Invalid server details for '{server_name}'. Ignoring.")
                continue

            command = server_details["command"]
            if command == "npx":
                if not self.npx_available:
                    logger.warning(f"MCPSM: npx is not available. Cannot load server '{server_name}'.")
                    continue
            elif command == "uvx":
                if not self.uvx_available:
                    logger.warning(f"MCPSM: uvx is not available. Cannot load server '{server_name}'.")
                    continue
                
            elif command == "node":
                if not self.node_available:
                    logger.warning(f"MCPSM: node is not available. Cannot load server '{server_name}'.")
                    continue

            self.servers[server_name] = MCPServer(
                name=server_name,
                command=command,
                args=server_details["args"],
                env=server_details.get("env", None),
                timeout=server_details.get("timeout", None),
                type=MCPServerType.Official,
            )
            logger.debug(f"MCPSM: Loaded official server: '{server_name}'.")

    def remove_server(self, server_name: str) -> None:
        """Remove a server from the available servers."""
        try:
            self.servers.pop(server_name)
            logger.info(f"MCPSM: Removed server: {server_name}")
        except KeyError:
            logger.warning(f"MCPSM: Server '{server_name}' not found. Cannot remove.")

    def get_server(self, server_name: str) -> Optional[MCPServer]:
        """Get the server by name."""
        return self.servers.get(server_name, None)
