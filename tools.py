from dataclasses import dataclass, field
from typing import Callable, Dict, Any, Optional
import subprocess

@dataclass
class ToolResult:
    content: str
    success: bool

@dataclass
class ToolMetadata:
    """Metadata for a tool that describes its purpose and parameters."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    required: Optional[list] = None

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, tuple[Callable, ToolMetadata]] = {}
    
    def register(self, name: str, func: Callable, metadata: ToolMetadata):
        """Register a tool with the given name, function and metadata."""
        self._tools[name] = (func, metadata)
    
    def call(self, name: str, args: dict) -> ToolResult:
        """Execute a registered tool with the provided arguments."""
        if name not in self._tools:
            return ToolResult(content=f"Tool '{name}' not found", success=False)
        
        func, _ = self._tools[name]
        try:
            result = func(**args)
            return result
        except Exception as e:
            return ToolResult(content=str(e), success=False)
    
    def to_ollama_tools(self) -> list[dict]:
        """Convert registered tools to Ollama format."""
        ollama_tools = []
        for name, (func, metadata) in self._tools.items():
            ollama_tool = {
                "type": "function",
                "function": {
                    "name": metadata.name,
                    "description": metadata.description,
                    "parameters": metadata.parameters
                }
            }
            ollama_tools.append(ollama_tool)
        return ollama_tools

def open_browser(url: str = "https://www.google.com") -> ToolResult:
    """Open Chrome or the default browser."""
    try:
        subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to make new window'], check=True)
        return ToolResult(content="Opened Chrome browser", success=True)
    except Exception as e:
        try:
            subprocess.run(["open", url], check=True)
            return ToolResult(content=f"Opened {url}", success=True)
        except Exception as e2:
            return ToolResult(content=f"Failed to open browser: {e2}", success=False)

def search_web(query: str) -> ToolResult:
    """Search the web for a query (stub implementation)."""
    return ToolResult(content=f"Search results for {query} (stub)", success=True)

# Default registry with initial tools
default_registry = ToolRegistry()
default_registry.register("open_browser", open_browser, ToolMetadata(
    name="open_browser",
    description="Open Chrome or the default browser",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to open in the browser"
            }
        },
        "required": []
    }
))
default_registry.register("search_web", search_web, ToolMetadata(
    name="search_web",
    description="Search the web for a query",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query"
            }
        },
        "required": ["query"]
    }
))