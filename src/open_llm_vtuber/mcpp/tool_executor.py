import json
import datetime
from loguru import logger
from typing import (
    Dict,
    Any,
    List,
    Literal,
    Union,
    Optional,
    AsyncIterator,
    Callable,
    Awaitable,
)

from .types import ToolCallObject
from .mcp_client import MCPClient
from .tool_manager import ToolManager


class ToolExecutor:
    def __init__(
        self,
        mcp_client: MCPClient,
        tool_manager: ToolManager,
        client_uid: str = None,
        websocket_send: Callable[[str], Awaitable[None]] = None,
    ):
        self._mcp_client = mcp_client
        self._tool_manager = tool_manager
        self._client_uid = client_uid
        self._websocket_send = websocket_send

    def parse_tool_call(self, call: Union[Dict[str, Any], ToolCallObject]) -> tuple:
        """Parse tool call from different formats.

        Returns:
            tuple: (tool_name, tool_id, tool_input, is_error, result_content, parse_error)
        """
        tool_name: str = ""
        tool_id: str = ""
        tool_input: Any = None
        is_error: bool = False
        result_content: str = ""
        parse_error: bool = False

        if isinstance(call, ToolCallObject):
            tool_name = call.function.name
            tool_id = call.id
            try:
                tool_input = json.loads(call.function.arguments)
            except json.JSONDecodeError:
                logger.error(
                    f"Failed to decode OpenAI tool arguments for '{tool_name}'"
                )
                result_content = (
                    f"Error: Invalid arguments format for tool '{tool_name}'."
                )
                is_error = True
                parse_error = True
        elif isinstance(call, dict):
            tool_id = call.get("id")
            tool_name = call.get("name")
            tool_input = call.get("input", call.get("args"))

            if tool_input is None:
                logger.warning(
                    f"Empty input for tool '{tool_name}' (ID: {tool_id}). Using empty object."
                )
                tool_input = {}

            if not tool_id or not tool_name:
                logger.error(f"Invalid Dict tool call structure: {call}")
                result_content = "Error: Invalid tool call structure from LLM."
                is_error = True
                parse_error = True
        else:
            logger.error(f"Unsupported tool call type: {type(call)}")
            result_content = "Error: Unsupported tool call type."
            is_error = True
            parse_error = True

        return tool_name, tool_id, tool_input, is_error, result_content, parse_error

    def format_tool_result(
        self,
        caller_mode: Literal["Claude", "OpenAI", "Prompt"],
        tool_id: str,
        result_content: str,
        is_error: bool,
    ) -> Dict[str, Any] | None:
        """Format tool result for LLM API."""
        if caller_mode == "Claude":
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_content,
                "is_error": is_error,
            }
        elif caller_mode == "OpenAI":
            return {"role": "tool", "tool_call_id": tool_id, "content": result_content}
        elif caller_mode == "Prompt":
            return {
                "tool_id": tool_id,
                "content": result_content,
                "is_error": is_error,
            }

    def process_tool_from_prompt_json(
        self, data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process tool data from JSON in prompt mode."""
        parsed_tools = []
        for item in data:
            server = item.get("mcp_server")
            tool_name = item.get("tool")
            arguments_str = item.get("arguments")
            if all([server, tool_name, arguments_str]):
                try:
                    args_dict = json.loads(arguments_str)
                    parsed_tools.append(
                        {
                            "name": tool_name,
                            "server": server,
                            "args": args_dict,
                            "id": f"prompt_tool_{len(parsed_tools)}",
                        }
                    )
                    logger.info(f"Parsed tool call from prompt JSON: {tool_name}")
                except json.JSONDecodeError:
                    logger.error(
                        f"Failed to decode arguments JSON in prompt mode tool call"
                    )
                except Exception as e:
                    logger.error(f"Error processing prompt mode tool dict: {e}")
            else:
                logger.warning(f"Skipping invalid tool structure in prompt mode JSON")
        return parsed_tools

    async def execute_tools(
        self,
        tool_calls: Union[List[Dict[str, Any]], List[ToolCallObject]],
        caller_mode: Literal["Claude", "OpenAI", "Prompt"],
        mcp_client: Optional[MCPClient] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Execute tools and yield status updates."""
        tool_results_for_llm = []

        if not mcp_client:
            logger.error("MCP Client not provided for tool execution.")
            for i, call in enumerate(tool_calls):
                tool_id = getattr(
                    call,
                    "id",
                    call.get(
                        "id",
                        f"error_{i}_{datetime.datetime.now(datetime.timezone.utc).isoformat()}",
                    ),
                )
                tool_name = getattr(call, "function.name", call.get("name", "Unknown"))
                error_content = "Error: Tool execution environment not configured."
                yield {
                    "type": "tool_call_status",
                    "tool_id": tool_id,
                    "tool_name": tool_name,
                    "status": "error",
                    "content": error_content,
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat()
                    + "Z",
                }

        logger.info(f"Executing {len(tool_calls)} tool(s) for {caller_mode} caller.")
        for call in tool_calls:
            (
                tool_name,
                tool_id,
                tool_input,
                is_error,
                result_content,
                parse_error,
            ) = self.parse_tool_call(call)

            if parse_error:
                logger.warning(
                    f"Skipping tool call due to parsing error: {result_content}"
                )
                yield {
                    "type": "tool_call_status",
                    "tool_id": tool_id
                    or f"parse_error_{datetime.datetime.now(datetime.timezone.utc).isoformat()}",
                    "tool_name": tool_name or "Unknown Tool",
                    "status": "error",
                    "content": result_content,
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat()
                    + "Z",
                }
            else:
                yield {
                    "type": "tool_call_status",
                    "tool_id": tool_id,
                    "tool_name": tool_name,
                    "status": "running",
                    "content": f"Input: {json.dumps(tool_input)}",
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat()
                    + "Z",
                }

                is_error, result_content, metadata = await self.run_single_tool(
                    mcp_client, tool_name, tool_id, tool_input
                )

                # Prepare tool call status update
                status_update = {
                    "type": "tool_call_status",
                    "tool_id": tool_id,
                    "tool_name": tool_name,
                    "status": "error" if is_error else "completed",
                    "content": result_content,
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat()
                    + "Z",
                }

                # For stagehand_navigate tool, include browser view links if available
                if tool_name == "stagehand_navigate" and not is_error:
                    live_view_data = metadata.get("liveViewData", {})
                    if live_view_data:
                        logger.info(
                            f"Found live view data for stagehand_navigate: {live_view_data}"
                        )
                        status_update["browser_view"] = live_view_data

                yield status_update

            formatted_result = self.format_tool_result(
                caller_mode, tool_id, result_content, is_error
            )
            if formatted_result:
                tool_results_for_llm.append(formatted_result)

        logger.info(
            f"Finished executing tools with {len(tool_results_for_llm)} results."
        )
        yield {"type": "final_tool_results", "results": tool_results_for_llm}

    async def run_single_tool(
        self, client: MCPClient, tool_name: str, tool_id: str, tool_input: Any
    ) -> tuple[bool, str, Dict[str, Any]]:
        """Run a single tool using MCPClient."""
        logger.info(f"Executing tool: {tool_name} (ID: {tool_id})")
        tool_info = self._tool_manager.get_tool(tool_name)
        is_error = False
        result_content = ""
        metadata = {}

        if tool_input is None:
            tool_input = {}

        if not tool_info:
            logger.error(f"Tool '{tool_name}' not found in ToolManager.")
            result_content = f"Error: Tool '{tool_name}' is not available."
            is_error = True
        elif not tool_info.related_server:
            logger.error(f"Tool '{tool_name}' does not have a related server defined.")
            result_content = f"Error: Configuration error for tool '{tool_name}'. No server specified."
            is_error = True
        else:
            try:
                result = await client.call_tool(
                    server_name=tool_info.related_server,
                    tool_name=tool_name,
                    tool_args=tool_input,
                )

                # Handle result as dictionary or string for backwards compatibility
                if isinstance(result, dict):
                    result_content = result.get("content", "")
                    metadata = result.get("metadata", {})
                else:
                    result_content = str(result)

                logger.info(f"Tool '{tool_name}' executed successfully.")
            except (ValueError, RuntimeError, ConnectionError) as e:
                logger.exception(f"Error executing tool '{tool_name}': {e}")
                result_content = f"Error executing tool '{tool_name}': {e}"
                is_error = True
            except Exception as e:
                logger.exception(f"Unexpected error executing tool '{tool_name}': {e}")
                result_content = f"Error executing tool '{tool_name}': {e}"
                is_error = True

        return is_error, result_content, metadata
