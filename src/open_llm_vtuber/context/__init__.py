"""
Context module - Separated components for ServiceContext

This module provides a clean separation of concerns for service context:
- EngineManager: Engine initialization and management
- MCPManager: MCP component management
- ServiceContext: Facade that integrates all managers
"""

from .engine_manager import EngineManager
from .mcp_manager import MCPManager
from .service_context import ServiceContext

__all__ = [
    "EngineManager",
    "MCPManager",
    "ServiceContext",
]
