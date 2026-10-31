from dataclasses import dataclass, field
from typing import Callable, Dict, Any, Optional
import datetime
import html as html_lib
import json
import os
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
            return ToolResult(content=f"Error executing tool '{name}': {e}", success=False)
    
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


# --- Tool Implementations -----------------------------------------------------

def get_current_time(timezone: str = "local") -> ToolResult:
    """Get the current exact local time, date, and day of the week."""
    now = datetime.datetime.now()
    text = now.strftime("%A, %B %d, %Y at %I:%M %p")
    return ToolResult(content=f"The current local time is {text}.", success=True)


def open_app(app_name: str) -> ToolResult:
    """Open or focus a macOS application by name (e.g., 'Calculator', 'Music', 'Safari', 'Terminal', 'Notes')."""
    if not app_name or not app_name.strip():
        return ToolResult(content="No application name specified.", success=False)
    cleaned = app_name.strip()
    try:
        subprocess.run(["open", "-a", cleaned], check=True)
        return ToolResult(content=f"Opened {cleaned}.", success=True)
    except subprocess.CalledProcessError:
        # Fallback to general open
        try:
            subprocess.run(["open", f"/Applications/{cleaned}.app"], check=True)
            return ToolResult(content=f"Opened {cleaned}.", success=True)
        except Exception as e:
            return ToolResult(content=f"Could not open application '{cleaned}': {e}", success=False)
    except Exception as e:
        return ToolResult(content=f"Could not open application '{cleaned}': {e}", success=False)


def get_weather(location: str = "current") -> ToolResult:
    """Get the live weather forecast and temperature for a city or region."""
    loc = location.strip() if location and location != "current" else ""
    safe_loc = urllib.parse.quote(loc)
    url = f"https://wttr.in/{safe_loc}?format=j1"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
            cur = data["current_condition"][0]
            desc = cur["weatherDesc"][0]["value"]
            temp_f = cur["temp_F"]
            temp_c = cur["temp_C"]
            humidity = cur["humidity"]
            feels_f = cur["FeelsLikeF"]
            area = location if location and location != "current" else "your current location"
            return ToolResult(
                content=f"Weather for {area}: {temp_f}°F ({temp_c}°C), {desc}. Feels like {feels_f}°F, humidity {humidity}%.",
                success=True
            )
    except Exception as e:
        return ToolResult(content=f"Unable to fetch weather for '{location}': {e}", success=False)


def control_media(action: str = "playpause") -> ToolResult:
    """Control media playback on macOS (playpause, next, previous, mute, louder, softer)."""
    act = action.lower().strip()
    if act in ("play", "pause", "playpause", "toggle"):
        cmd = 'tell application "Music" to playpause'
        msg = "Toggled music playback."
    elif act in ("next", "skip"):
        cmd = 'tell application "Music" to next track'
        msg = "Skipped to next track."
    elif act in ("prev", "previous", "back"):
        cmd = 'tell application "Music" to previous track'
        msg = "Returned to previous track."
    elif "louder" in act or "up" in act:
        cmd = 'set volume output volume ((output volume of (get volume settings)) + 10)'
        msg = "Turned volume up."
    elif "softer" in act or "down" in act:
        cmd = 'set volume output volume ((output volume of (get volume settings)) - 10)'
        msg = "Turned volume down."
    elif "mute" in act:
        cmd = 'set volume with output muted'
        msg = "Muted system audio."
    else:
        cmd = 'tell application "Music" to playpause'
        msg = "Toggled music."

    try:
        subprocess.run(["osascript", "-e", cmd], check=True)
        return ToolResult(content=msg, success=True)
    except Exception as e:
        return ToolResult(content=f"Failed to control media ({action}): {e}", success=False)


def open_browser(url: str = "https://www.google.com") -> ToolResult:
    """Open Chrome or the default browser to a URL."""
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
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


# --- Register Default Assistant Tools -----------------------------------------

default_registry = ToolRegistry()

default_registry.register("get_current_time", get_current_time, ToolMetadata(
    name="get_current_time",
    description="Get the current exact local time, date, and day of the week.",
    parameters={
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Optional timezone name (default 'local')"
            }
        },
        "required": []
    }
))

default_registry.register("open_app", open_app, ToolMetadata(
    name="open_app",
    description="Open or focus a macOS application on the computer (Calculator, Music, Safari, Terminal, Notes, etc.).",
    parameters={
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "The exact name of the application to launch (e.g. 'Calculator')"
            }
        },
        "required": ["app_name"]
    }
))

default_registry.register("get_weather", get_weather, ToolMetadata(
    name="get_weather",
    description="Get live weather forecast and temperature for any city, state, or location.",
    parameters={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The city or location name (e.g. 'Austin', 'London', 'Tokyo')"
            }
        },
        "required": ["location"]
    }
))

default_registry.register("control_media", control_media, ToolMetadata(
    name="control_media",
    description="Control macOS media playback or system audio (playpause, next, previous, louder, softer, mute).",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "The action: 'playpause', 'next', 'previous', 'louder', 'softer', or 'mute'"
            }
        },
        "required": ["action"]
    }
))

default_registry.register("open_browser", open_browser, ToolMetadata(
    name="open_browser",
    description="Open a website in Chrome or the default browser.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full website URL to open"
            }
        },
        "required": ["url"]
    }
))

default_registry.register("search_web", search_web, ToolMetadata(
    name="search_web",
    description="Search the web for current events, facts, news, and queries.",
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
