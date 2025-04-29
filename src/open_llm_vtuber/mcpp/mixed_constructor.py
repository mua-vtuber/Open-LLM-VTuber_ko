"""Constructs prompts for servers and tools, formats tool information for OpenAI API."""

import json
import os.path

from typing import Dict, Optional
from pathlib import Path
from loguru import logger

from .types import MCPServerPrompt, FormattedTool
from .client import MCPClient
from .server_manager import MCPServerManager
from .tool_manager import ToolManager
from .utils.path import validate_file

DEFAULT_SERVERS_PROMPT_PATH = Path(__file__).parent / "configs" / "servers_prompt.json"
DEFAULT_FORMATTED_TOOLS_PATH = (
    Path(__file__).parent / "configs" / "formatted_tools.json"
)

DEFAULT_FILES_PATH = {
    "servers_prompt": DEFAULT_SERVERS_PROMPT_PATH,
    "formatted_tools": DEFAULT_FORMATTED_TOOLS_PATH,
}


class MixedConstructor:
    """Manages prompts for MCP servers and standardizes tool information."""

    def __init__(
        self,
        prompt_paths: Dict[str, str | Path] = DEFAULT_FILES_PATH,
        server_manager: Optional[MCPServerManager] = None,
        tool_manager: Optional[ToolManager] = None,
    ) -> None:
        """Initialize with paths to prompt files and managers."""
        configs_dir = Path(__file__).parent / "configs"
        configs_dir.mkdir(exist_ok=True)
        
        servers_prompt_path = prompt_paths.get("servers_prompt", DEFAULT_SERVERS_PROMPT_PATH)
        if isinstance(servers_prompt_path, str):
            servers_prompt_path = Path(servers_prompt_path)
        
        servers_prompt_path.parent.mkdir(exist_ok=True)
        if not servers_prompt_path.exists():
            servers_prompt_path.write_text("{}", encoding="utf-8")
            
        formatted_tools_path = prompt_paths.get("formatted_tools", DEFAULT_FORMATTED_TOOLS_PATH)
        if isinstance(formatted_tools_path, str):
            formatted_tools_path = Path(formatted_tools_path)
            
        formatted_tools_path.parent.mkdir(exist_ok=True)
        if not formatted_tools_path.exists():
            formatted_tools_path.write_text("{}", encoding="utf-8")
            
        servers_prompt_path.write_text("{}", encoding="utf-8")
        formatted_tools_path.write_text("{}", encoding="utf-8")
        
        self.servers_prompt = validate_file(servers_prompt_path)

        self.prompts: Dict[str, Dict[str, str | float] | MCPServerPrompt] = json.loads(
            self.servers_prompt.read_text(encoding="utf-8")
        )

        self.server_manager = server_manager or MCPServerManager()
        self.tool_manager = tool_manager or ToolManager(formatted_tools_path)

        # Structure: server name -> tool name -> tool details (description, parameters, required)
        self.servers_info: Dict[str, Dict[str, str]] = {}

        self._preprocess_prompts()

    def _preprocess_prompts(self) -> None:
        """Convert prompt data to MCPServerPrompt objects."""
        for server_name, prompt in self.prompts.items():
            if isinstance(prompt, dict):
                content = prompt.get("content", None)
                mtime = prompt.get("mtime", None)

                if content and mtime:
                    self.prompts[server_name] = MCPServerPrompt(
                        content=content, mtime=mtime
                    )
                    continue

            logger.warning(f"MC: Invalid prompt format for server '{server_name}'")

    def _reformat_prompts_to_dict(self) -> None:
        """Convert MCPServerPrompt objects to dictionaries."""
        for server_name, prompt in self.prompts.items():
            if isinstance(prompt, MCPServerPrompt):
                self.prompts[server_name] = {
                    "content": prompt.content,
                    "mtime": prompt.mtime,
                }
                continue

            logger.warning(f"MC: Invalid prompt format for server '{server_name}'")

    def _reformat_tools_to_dict(self) -> None:
        """Convert FormattedTool objects to dictionaries."""
        for tool_name, tool_info in self.tool_manager.tools.items():
            if isinstance(tool_info, FormattedTool):
                self.tool_manager.tools[tool_name] = {
                    "input_schema": tool_info.input_schema,
                    "related_server": tool_info.related_server,
                    "generic_schema": tool_info.generic_schema,
                    "description": tool_info.description,
                }
                continue

            logger.warning(f"MC: Invalid tool format for '{tool_name}'")

    def _dump_prompts(self) -> None:
        """Save prompts to file."""
        self._reformat_prompts_to_dict()
        self.servers_prompt.write_text(
            json.dumps(self.prompts, indent=4), encoding="utf-8"
        )

    def _dump_tools(self) -> None:
        """Save tools to file."""
        self._reformat_tools_to_dict()
        self.tool_manager.formatted_tools_path.write_text(
            json.dumps(self.tool_manager.tools, indent=4), encoding="utf-8"
        )

    async def get_servers_info(self) -> None:
        """Fetch tool information from MCP servers."""
        for server_name in self.server_manager.servers.keys():
            try:
                async with MCPClient(self.server_manager) as client:
                    self.servers_info[server_name] = {}
                    tools = await client.list_tools(server_name)
                    for tool in tools:
                        self.servers_info[server_name][tool.name] = {}
                        tool_info = self.servers_info[server_name][tool.name]
                        tool_info["description"] = tool.description
                        tool_info["parameters"] = tool.inputSchema.get("properties", {})
                        tool_info["required"] = tool.inputSchema.get("required", [])
                        self.tool_manager.tools[tool.name] = FormattedTool(
                            input_schema=tool.inputSchema,
                            related_server=server_name,
                            description=tool.description,
                        )
            except (ValueError, RuntimeError, ConnectionError) as e:
                logger.error(f"MC: Failed to get info for server '{server_name}': {e}")
                if server_name not in self.servers_info:
                    self.servers_info[server_name] = {}
                continue
            except Exception as e:
                logger.error(f"MC: Unexpected error for server '{server_name}': {e}")
                if server_name not in self.servers_info:
                    self.servers_info[server_name] = {}
                continue

    def construct_servers_prompt(self) -> None:
        """Build prompt for each server and its tools."""
        for server_name, tools in self.servers_info.items():
            mtime = -1

            prompt_content = f"Server: {server_name}\\n"
            prompt_content += "    Tools:\\n"
            for tool_name, tool_info in tools.items():
                prompt_content += f"        {tool_name}:\\n"
                prompt_content += f"            Description: {tool_info['description']}\\n"
                prompt_content += "            Parameters:\\n"
                for param_name, param_info in tool_info["parameters"].items():
                    description = param_info.get("description")
                    description = (
                        description
                        if description
                        else param_info.get("title", "No description provided.")
                    )
                    prompt_content += f"                {param_name}:\\n"
                    prompt_content += f"                    Type: {param_info['type']}\\n"
                    prompt_content += f"                    Description: {description}\\n"
                if tool_info["required"]:
                    prompt_content += (
                        f"            Required: {', '.join(tool_info['required'])}\\n"
                    )

            self.prompts[server_name] = MCPServerPrompt(content=prompt_content, mtime=mtime)
            logger.info(f"MC: Constructed prompt for server '{server_name}'.")

        self._dump_prompts()

    def format_tools(self) -> None:
        """Format tools to OpenAI function-calling compatible schema."""
        for tool_name in self.tool_manager.tools.keys():
            data_object = self.tool_manager.tools.get(tool_name, None)
            if isinstance(data_object, FormattedTool):
                input_schema = data_object.input_schema
                properties: Dict[str, Dict[str, str]] = input_schema.get(
                    "properties", {}
                )
                tool_description = data_object.description
                data_object.generic_schema = {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": tool_description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                param_name: {
                                    "type": param_info.get("type", "string"),
                                    "description": param_info.get(
                                        "description",
                                        param_info.get(
                                            "title", "No description provided."
                                        ),
                                    ),
                                }
                                for param_name, param_info in properties.items()
                            },
                            "required": input_schema.get("required", []),
                        },
                    },
                }
            else:
                logger.warning(f"MC: Invalid tool format for '{tool_name}'")

        self._dump_tools()

    async def run(self) -> None:
        """Run the complete process."""
        await self.get_servers_info()
        self.construct_servers_prompt()
        self.format_tools()

# if __name__ == "__main__":
#     import asyncio
#     prompt_constructor = MixedConstructor()
#     asyncio.run(prompt_constructor.run())
#     logger.info("PC: Prompt construction completed.")
