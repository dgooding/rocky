from dataclasses import dataclass
from typing import Callable, Dict
import subprocess

@dataclass
class ToolResult:
    content: str
    success: bool

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
    
    def register(self, name: str, func: Callable):
        """Register a tool with the given name and function."""
        self._tools[name] = func
    
    def call(self, name: str, args: dict) -> ToolResult:
        """Execute a registered tool with the provided arguments."""
        if name not in self._tools:
            return ToolResult(content=f"Tool '{name}' not found", success=False)
        
        try:
            result = self._tools[name](**args)
            return result
        except Exception as e:
            return ToolResult(content=str(e), success=False)

def open_browser(url: str) -> ToolResult:
    """Open a URL in the default browser."""
    try:
        subprocess.run(["open", url], check=True)
        return ToolResult(content=f"Opened {url}", success=True)
    except subprocess.CalledProcessError as e:
        return ToolResult(content=f"Failed to open {url}: {e}", success=False)

def search_web(query: str) -> ToolResult:
    """Search the web for a query (stub implementation)."""
    return ToolResult(content=f"Search results for {query} (stub)", success=True)

# Default registry with initial tools
default_registry = ToolRegistry()
default_registry.register("open_browser", open_browser)
default_registry.register("search_web", search_web)