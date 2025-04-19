from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path


class MCPServerType(str, Enum):
    """Enum for MCP Server Types."""

    Official = 0
    Custom = 1


@dataclass
class MCPServerPrompt:
    
    content: str
    mtime: Optional[float] = None


@dataclass
class MCPServer:
    
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    timeout: Optional[timedelta] = timedelta(seconds=10)
    type: MCPServerType = MCPServerType.Custom
    path: Optional[Path] = None
    

@dataclass
class FormattedTool:
    
    input_schema: Dict[str, Any]
    related_server: str
    generic_schema: Optional[Dict[str, Any]] = None