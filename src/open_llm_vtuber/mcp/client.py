"""MCP Client for Open-LLM-Vtuber.

Reference: https://modelcontextprotocol.io/quickstart/client
"""

from contextlib import AsyncExitStack
from typing import Optional, Dict
from pathlib import Path
from loguru import logger

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

try:
    from .server_manager import MCPServerManager
except ImportError:
    from server_manager import MCPServerManager


class MCPClient:
    
    """MCP Client for Open-LLM-Vtuber.
    
    Usage:
    1. By async context manager:
    ```python
    async with MCPClient(auto_search=True) as client:
        await client.connect_to_server("example")
    ```
    2. By manual:
    ```python
    client = MCPClient(auto_search=True)
    await client.connect_to_server("example")
    await client.close()
    ```
    """
    
    def __init__(self, server_manager: MCPServerManager) -> None:
        """Initialize the MCP Client.
        
        Args:
            server_manager (MCPServerManager): The server manager to use for managing servers.
        
        Raises:
            ValueError: If the server manager is not an instance of MCPServerManager.
        """
        self.session: Optional[ClientSession] = None
        self.exit_stack: AsyncExitStack = AsyncExitStack()
        self.stdio, self.write = None, None
        self.servers: Dict[str, Path] = {}
        
        if isinstance(server_manager, MCPServerManager):
            self.server_manager = server_manager
        else:
            raise ValueError("MCPC: Invalid server manager. Must be an instance of MCPServerManager.")
    
    
    @logger.catch
    async def connect_to_server(self, server_name: str) -> None:
        """Connect to the specified server.
        
        Args:
            server_name (str): The name of the server to connect to.
        
        Raises:
            ValueError: If the server is not found in the available servers or not supported.
            RuntimeError: If node.js is not found in PATH and the server is a JavaScript server.
        """
        logger.info(f"MCPC: Attempting to connect to server '{server_name}' ...")
        # Initialize the server parameters.
        server = self.server_manager.get_server(server_name)
        if not server:
            logger.error(f"MCPC: Server '{server_name}' not found in available servers.")
            raise ValueError(f"MCPC: Server '{server_name}' not found in available servers.")
        
        executable = server["executable"]
        args = server["args"]
            
        server_params = StdioServerParameters(
            command=executable,
            args=args,
        )
        
        # Intialize the session.
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(
                self.stdio, self.write
            )
        )
        await self.session.initialize()
        
        response = await self.session.list_tools()
        tools = response.tools
        logger.info(f"MCPC: Connected to server '{server_name}'. Available tools: {tools}")
    
    
    async def close(self) -> None:
        """Clean up the MCP client."""
        await self.exit_stack.aclose()
    
    
    async def __aenter__(self) -> "MCPClient":
        """Enter the async context manager."""
        return self

    
    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Exit the async context manager."""
        await self.close()
        if exc_type:
            logger.error(f"MCPC: Exception occurred: {exc_value}")
        if traceback:
            logger.error(f"MCPC: Traceback: {traceback}")


if __name__ == "__main__":
    # Test the MCPClient.
    import asyncio
    
    server_manager = MCPServerManager()
    
    async def main():
        async with MCPClient(server_manager) as client:
            await client.connect_to_server("example")
            
    asyncio.run(main())