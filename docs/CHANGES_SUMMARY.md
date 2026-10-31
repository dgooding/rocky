# Changes Summary

I have successfully integrated the ToolRegistry from `tools.py` into `rocky_desktop_app.py` as requested. Here are the key changes:

## 1. Import Statement
- Added `from tools import ToolRegistry` to the import section at the top of the file

## 2. Brain Initialization
- Added `self.tools = ToolRegistry()` in the `Brain.__init__` method to initialize the tool registry

## 3. System Prompt Update
- Updated `SYSTEM_PROMPT` to include instructions for the LLM to use the tool call format:
  `<tool_call name="tool_name" args='{"arg1": "val1", "arg2": "val2"}' />`

## 4. Brain.stream Implementation
- Completely rewrote the `Brain.stream` method to:
  - Use a buffering mechanism for fragmented tool_call tags
  - Detect complete tool call tags in streaming responses
  - Yield preceding text before tool calls
  - Execute tools using `self.tools.call(name, args)`
  - Update history with both the tool call and its result
  - Restart the generation loop to get subsequent response from the LLM 
  - Handle edge cases like empty chunks or unexpected sequences

## Key Features of Implementation:
- Proper handling of tool call fragmentation across streaming chunks
- Error handling for malformed tool calls
- History management for tool interactions
- Maintains all existing functionality while adding tool execution capabilities
- Follows the exact specified format for tool calls with single-quoted JSON args

The changes are contained in a single file as required and fully implement the requested tool integration functionality.