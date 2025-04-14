"""MCP Server Manager for Open-LLM-Vtuber.

This module provides a server manager for MCP servers.
"""

import shutil
import sys
import json

from pathlib import Path
from typing import Dict, Optional, Union, Sequence
from loguru import logger

try:
    from .utils.path import validate_file
except ImportError:
    from utils.path import validate_file

DEFAULT_CONFIG_PATH = Path(__file__).parent / "configs" / "mcp_servers.json"

class MCPServerManager:
    """MCP Server Manager for managing server files.
    
    This class handles the discovery, validation, and management of MCP server files.
    """
    
    def __init__(self, config_path: str | Path = DEFAULT_CONFIG_PATH) -> None:
        """Initialize the MCP Server Manager.
        
        Args:
            config_path (str | Path): The path to the configuration file.
                Default is './configs/mcp_servers.json'.
        """
        # Check if the config path is valid json file.
        try:
            config_path = validate_file(config_path, ".json")
        except ValueError:
            logger.error(f"MCPSM: File '{config_path}' does not exist, or is not a json file.")
            raise ValueError(f"MCPSM: File '{config_path}' does not exist, or is not a json file.")

        self.config: Dict[str, Union[str, dict]] = json.loads(config_path.read_text(encoding="utf-8"))
        
        # Structure of self.servers (also self.config["officials"]):
        # {
        #     "mcp_server_name": {
        #         "executable": "python(sys.executable) | uvx | node | npx",
        #         "args": [
        #             "path/to/server.py | path/to/server.js | @modelcontextprotocol/server | module-name",
        #             "--other",
        #             "args",
        #         ]
        #     },
        # }
        self.servers: Dict[str, Dict[str, Union[str, Sequence[str]]]] = {}
        
        # Check node.js/uv runtime availability
        # as npx/uvx can be used to run 'officials' TypeScript/Python servers.
        # Find servers at https://github.com/modelcontextprotocol/servers
        self.npx_available = self._detect_runtime("npx")
        self.uvx_available = self._detect_runtime("uvx")
        
        self.search_custom_servers()
        self.load_official_servers()
    
    
    def _detect_runtime(self, target: str) -> bool:
        """Check if a runtime is available in the system PATH."""
        founded = shutil.which(target)
        if founded:
            return True
        return False
    
    
    def search_custom_servers(self) -> None:
        """Search for available mcp servers in the custom directory.  
        Stores the server in `self.servers` in a specific format.
        
        Suported suffixes are:
        - .py: Python files
        - .js: TypeScript(Compiled) files
        """
        custom_servers_path = Path(self.config["custom_servers_path"])
        if not custom_servers_path.is_absolute():
            custom_servers_path = Path(__file__).parent / custom_servers_path
        custom_servers_path = custom_servers_path.absolute()
            
        if not custom_servers_path.exists() or not custom_servers_path.is_dir():
            logger.error(f"MCPSM: Path '{custom_servers_path}' does not exist, or is not a directory.")
            logger.error("MCPSM: Please check your configuration file.")
            raise ValueError(
                f"MCPSM: Path '{custom_servers_path}' does not exist, or is not a directory."
                "Please check your configuration file."
            )
        
        for path in custom_servers_path.iterdir():
            if path.suffix == ".py":
                server_name = path.stem
                self.servers[server_name] = {
                    "executable": sys.executable,
                    "args": [str(path)]
                }
                logger.debug(f"MCPSM: Found custom server: {server_name}.py")
            elif path.suffix == ".js":
                if not self.npx_available:
                    logger.warning(f"Found TypeScript server '{server_name}.js' but node is not available.")
                    logger.warning("So it will not be added to the available servers.")
                    continue
                self.servers[server_name] = {
                    "executable": "node",
                    "args": [str(path)]
                }
            else:
                logger.debug(f"MCPSM: Found unsupported file '{path.name}'. Ignoring.")
                continue
    
    
    def load_official_servers(self) -> None:
        """Load official servers from the config file.
        
        The config file should follow the original structure.
        """
        officials = self.config.get("officials", {})
        if officials == {}:
            logger.warning("MCPSM: No official servers found in the config file.")
            return
        
        for server_name, server_details in officials.items():
            if "command" not in server_details or "args" not in server_details:
                logger.warning(f"MCPSM: Invalid server details for '{server_name}'. Ignoring.")
                continue
            
            executable = server_details["command"]
            if executable == "npx":
                if not self.npx_available:
                    logger.warning(f"MCPSM: npx is not available. Cannot load server '{server_name}'.")
                    continue
            elif executable == "uvx":
                if not self.uvx_available:
                    logger.warning(f"MCPSM: uvx is not available. Cannot load server '{server_name}'.")
                    continue
            
            self.servers[server_name] = {
                "executable": server_details["command"],
                "args": server_details["args"],
                "env": server_details.get("env", None),
            }
            logger.debug(f"MCPSM: Loaded official server: {server_name}.")
    
    
    def remove_server(self, server_name: str) -> None:
        """Remove a server from the available servers.
        
        Args:
            server_name (str): The name of the server to remove.
            
        Returns:
            bool: True if the server was removed, False if it wasn't found.
        """
        try:
            self.servers.pop(server_name)
            logger.info(f"MCPSM: Removed server: {server_name}")
        except KeyError:
            logger.warning(f"MCPSM: Server '{server_name}' not found. Cannot remove.")
    
    
    def get_server(self, server_name: str) -> Optional[Path]:
        """Get the path of a server by name.
        
        Args:
            server_name (str): The name of the server.
            
        Returns:
            Optional[Path]: The path of the server, or None if not found.
        """
        return self.servers.get(server_name, None)
    