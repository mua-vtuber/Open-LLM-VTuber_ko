"""MCP (Model Context Protocol) component management."""

from typing import Callable, List
from loguru import logger

from ..mcpp.server_registry import ServerRegistry
from ..mcpp.tool_manager import ToolManager
from ..mcpp.mcp_client import MCPClient
from ..mcpp.tool_executor import ToolExecutor
from ..mcpp.tool_adapter import ToolAdapter


class MCPManager:
    """Manages MCP (Model Context Protocol) components."""

    def __init__(self):
        self.server_registry: ServerRegistry | None = None
        self.tool_adapter: ToolAdapter | None = None
        self.tool_manager: ToolManager | None = None
        self.mcp_client: MCPClient | None = None
        self.tool_executor: ToolExecutor | None = None
        self.mcp_prompt: str = ""

    async def initialize(
        self,
        use_mcpp: bool,
        enabled_servers: List[str],
        send_text: Callable,
        client_uid: str,
    ) -> None:
        """
        Initialize MCP components based on configuration.

        Args:
            use_mcpp: Whether to use MCP
            enabled_servers: List of enabled MCP server names
            send_text: Callback function for sending text
            client_uid: Client unique identifier
        """
        logger.debug(
            f"Initializing MCP components: use_mcpp={use_mcpp}, enabled_servers={enabled_servers}"
        )

        # Reset MCP components first
        self._reset_components()

        if use_mcpp and enabled_servers:
            await self._init_components(enabled_servers, send_text, client_uid)
        elif use_mcpp and not enabled_servers:
            logger.warning(
                "use_mcpp is True, but mcp_enabled_servers list is empty. "
                "MCP components not initialized."
            )
        else:
            logger.debug(
                "MCP components not initialized (use_mcpp is False or no enabled servers)."
            )

    def _reset_components(self) -> None:
        """Reset all MCP components to initial state."""
        self.server_registry = None
        self.tool_manager = None
        self.mcp_client = None
        self.tool_executor = None
        self.mcp_prompt = ""

    async def _init_components(
        self,
        enabled_servers: List[str],
        send_text: Callable,
        client_uid: str,
    ) -> None:
        """Initialize all MCP components."""
        # 1. Initialize ServerRegistry
        self.server_registry = ServerRegistry()
        logger.info("ServerRegistry initialized.")

        # 2. Ensure ToolAdapter exists
        if not self.tool_adapter:
            logger.error(
                "ToolAdapter not initialized before calling MCP initialization."
            )
            self.mcp_prompt = "[Error: ToolAdapter not initialized]"
            return

        # 3. Get tools from ToolAdapter
        try:
            await self._init_tool_manager(enabled_servers)
        except Exception as e:
            logger.error(
                f"Failed during dynamic MCP tool construction: {e}", exc_info=True
            )
            self.tool_manager = None
            self.mcp_prompt = "[Error constructing MCP tools/prompt]"

        # 4. Initialize MCPClient
        self._init_mcp_client(send_text, client_uid)

        # 5. Initialize ToolExecutor
        self._init_tool_executor()

        logger.info("MCP components initialization complete.")

    async def _init_tool_manager(self, enabled_servers: List[str]) -> None:
        """Initialize the ToolManager with fetched tools."""
        (
            mcp_prompt_string,
            openai_tools,
            claude_tools,
        ) = await self.tool_adapter.get_tools(enabled_servers)

        self.mcp_prompt = mcp_prompt_string
        logger.info(
            f"Dynamically generated MCP prompt string (length: {len(self.mcp_prompt)})."
        )
        logger.info(
            f"Dynamically formatted tools - OpenAI: {len(openai_tools)}, Claude: {len(claude_tools)}."
        )

        _, raw_tools_dict = await self.tool_adapter.get_server_and_tool_info(
            enabled_servers
        )
        self.tool_manager = ToolManager(
            formatted_tools_openai=openai_tools,
            formatted_tools_claude=claude_tools,
            initial_tools_dict=raw_tools_dict,
        )
        logger.info("ToolManager initialized with dynamically fetched tools.")

    def _init_mcp_client(self, send_text: Callable, client_uid: str) -> None:
        """Initialize the MCPClient."""
        if self.server_registry:
            self.mcp_client = MCPClient(
                self.server_registry, send_text, client_uid
            )
            logger.info("MCPClient initialized for this session.")
        else:
            logger.error(
                "MCP enabled but ServerRegistry not available. MCPClient not created."
            )
            self.mcp_client = None

    def _init_tool_executor(self) -> None:
        """Initialize the ToolExecutor."""
        if self.mcp_client and self.tool_manager:
            self.tool_executor = ToolExecutor(self.mcp_client, self.tool_manager)
            logger.info("ToolExecutor initialized for this session.")
        else:
            logger.warning(
                "MCPClient or ToolManager not available. ToolExecutor not created."
            )
            self.tool_executor = None

    def ensure_tool_adapter(self, server_registry: ServerRegistry) -> None:
        """Ensure ToolAdapter is initialized."""
        if not self.tool_adapter:
            if not self.server_registry:
                self.server_registry = server_registry
            logger.info("Initializing ToolAdapter.")
            self.tool_adapter = ToolAdapter(server_registery=self.server_registry)

    async def close(self) -> None:
        """Clean up MCP resources."""
        if self.mcp_client:
            logger.info("Closing MCPClient...")
            await self.mcp_client.aclose()
            self.mcp_client = None
        logger.info("MCPManager closed.")
