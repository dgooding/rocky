from dataclasses import dataclass, field
from typing import Callable, Dict, Any, Optional
import html as html_lib
import re
import subprocess
import urllib.parse
import urllib.request

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
    
    def call(self, name: str, args: dict | None) -> ToolResult:
        """Execute a registered tool with the provided arguments."""
        if name not in self._tools:
            return ToolResult(content=f"Tool '{name}' not found", success=False)
        
        func, _ = self._tools[name]
        try:
            if not isinstance(args, dict):
                args = {}
            result = func(**args)
            if isinstance(result, ToolResult):
                return result
            return ToolResult(content=str(result), success=True)
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
    """Open Chrome or the default browser to a URL."""
    try:
        subprocess.run(["open", url], check=True)
        return ToolResult(content=f"Opened {url}", success=True)
    except Exception as e:
        return ToolResult(content=f"Failed to open browser: {e}", success=False)

def search_web(query: str, max_results: int = 3) -> ToolResult:
    """Search the web via DuckDuckGo Lite without external API keys."""
    if not query or not query.strip():
        return ToolResult(content="No search query provided.", success=False)
    data = urllib.parse.urlencode({"q": query.strip()}).encode()
    req = urllib.request.Request(
        "https://lite.duckduckgo.com/lite/",
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            snippets = re.findall(r"class=[\"']result-snippet[\"']>(.*?)</td>", body, re.DOTALL)
            results = []
            for s in snippets[:max_results]:
                text = html_lib.unescape(re.sub(r"<[^>]+>", "", s)).strip()
                if text:
                    results.append(text)
            if not results:
                return ToolResult(content=f"No results found for '{query}'.", success=True)
            return ToolResult(content="\n\n".join(results), success=True)
    except Exception as e:
        return ToolResult(content=f"Search failed: {e}", success=False)

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