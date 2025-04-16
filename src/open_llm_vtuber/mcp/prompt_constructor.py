"""As there are many different servers and tools,
we need to construct the prompt for each server and its tools.
"""

import json

from typing import Dict
from pathlib import Path
from loguru import logger

from .client import MCPClient
from .server_manager import MCPServerManager
from .utils.path import validate_file

DEFAULT_PROMPTS_PATH = Path(__file__).parent / "configs" / "servers_prompt.json"


class PromptConstructor:
    """Construct prompts for MCP servers and tools."""

    def __init__(self, prompts_path: str | Path = DEFAULT_PROMPTS_PATH) -> None:
        """Initialize the Prompt Constructor.

        Args:
            prompts_path (str | Path): The path to the directory containing the server prompts.
                Default is './configs/servers_prompt.json'.
        """
        # Check if the prompts path is valid json file.
        try:
            self.prompts_path = validate_file(prompts_path, ".json")
        except ValueError:
            logger.error(
                f"PC: File '{prompts_path}' does not exist, or is not a json file."
            )
            raise ValueError(
                f"PC: File '{self.prompts_path}' does not exist, or is not a json file."
            )

        self.prompts: Dict[str, str] = json.loads(
            self.prompts_path.read_text(encoding="utf-8")
        )
        self.server_manager = MCPServerManager()

        self.servers_info: Dict[str, Dict[str, str]] = {}

    async def get_servers_info(self) -> None:
        """Get the server information from the MCP servers."""
        for server_name in self.server_manager.servers.keys():
            async with MCPClient(self.server_manager) as client:
                try:
                    await client.connect_to_server(server_name)
                except Exception as e:
                    logger.error(
                        f"PC: Failed to connect to server '{server_name}': {e}"
                    )
                    logger.error(f"PC: Passing server '{server_name}'")
                    continue
                self.servers_info[server_name] = {}
                tools = await client.list_tools()
                for tool in tools:
                    self.servers_info[server_name][tool.name] = {}
                    tool_info = self.servers_info[server_name][tool.name]
                    tool_info["description"] = tool.description
                    tool_info["parameters"] = tool.inputSchema.get("properties", {})
                    tool_info["required"] = tool.inputSchema.get("required", [])

    def construct_prompt(self, force: bool = False) -> None:
        """Construct the prompt for each server and its tools.
        
        Args:
            force (bool, optional): If True, reconstruct prompts for all servers, 
                even if they already exist in the prompts dictionary. 
                If False, skip servers that already have prompts defined.
                Default is False.
        """
        for server_name, tools in self.servers_info.items():
            if server_name in self.prompts and not force:
                logger.info(
                    f"PC: Prompt for server '{server_name}' already exists. Skipping..."
                )
                continue

            prompt = f"Server: {server_name}\n"
            prompt += "    Tools:\n"
            for tool_name, tool_info in tools.items():
                prompt += f"        {tool_name}:\n"
                prompt += f"            Description: {tool_info['description']}\n"
                prompt += "            Parameters:\n"
                for param_name, param_info in tool_info["parameters"].items():
                    description = param_info.get("description")
                    description = (
                        description
                        if description
                        else param_info.get("title", "No description provided.")
                    )
                    prompt += f"                {param_name}:\n"
                    prompt += f"                    Type: {param_info['type']}\n"
                    prompt += f"                    Description: {description}\n"
                if tool_info["required"]:
                    prompt += (
                        f"            Required: {', '.join(tool_info['required'])}\n"
                    )

            self.prompts[server_name] = prompt

    def dump_prompts(self) -> None:
        """Dump the constructed prompts to the prompts file."""
        self.prompts_path.write_text(
            json.dumps(self.prompts, indent=4), encoding="utf-8"
        )
        logger.info(f"PC: Dumped prompts to '{self.prompts_path}'")

    async def run(self, force: bool = True) -> None:
        """Run the prompt constructor asynchronously."""
        await self.get_servers_info()
        self.construct_prompt(force)
        self.dump_prompts()


# if __name__ == "__main__":
#     import asyncio
#     prompt_constructor = PromptConstructor()
#     asyncio.run(prompt_constructor.run())
#     logger.info("PC: Prompt construction completed.")
