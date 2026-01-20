"""
Service Context - Backward compatibility re-export.

This module re-exports from the new context package for backward compatibility.
The actual implementation is now in the context/ package with clean separation of concerns.

New structure:
- context/engine_manager.py - AI engine initialization and management
- context/mcp_manager.py - MCP component management
- context/service_context.py - Facade integrating all managers
"""

# Re-export for backward compatibility
from .context import ServiceContext

# Also export the utility function for backward compatibility
from .context.service_context import deep_merge

__all__ = ["ServiceContext", "deep_merge"]
