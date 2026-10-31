"""Rocky's Brain module: LLM generation, tool execution loop, and sentence streaming.

Supports local Ollama, OpenAI-compatible APIs, and Anthropic.
Handles automatic tool execution and multi-turn tool continuations.
"""
from __future__ import annotations

import base64
import datetime
import http.client
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from tools import ToolRegistry, default_registry

SYSTEM_PROMPT = (
    "You are a helpful personal assistant. Speak in natural, contemporary "
    "British English. For a straightforward question, answer directly in one "
    "short sentence, ideally under 15 words. When the user asks for a "
    "description, detail, or continuation, give a clear, well-organized answer "
    "with enough concrete facts and context to satisfy that request. Do not "
    "restate the question, narrate your reasoning, or add unsolicited tips or "
    "follow-up offers. Avoid roleplay, catchphrases, and exaggerated emotion. "
    "Do not claim to be human; answer honestly if asked whether you are an AI. "
    "When asked to open a browser, apps, or execute system actions, ALWAYS use this tool call format: "
    "<tool_call name=\"open_browser\" args='{\"url\": \"https://www.google.com\"}' />"
)

VISION_PROMPT = "In one short sentence, describe the main thing you see."

DETAIL_REQUEST_PATTERN = re.compile(
    r"\b(describe|descriptive|explain|detail|detailed|everything|in depth|"
    r"long|thorough|elaborate|continue|keep going|tell me more|more about|"
    r"step by step|compare|list|summari[sz]e)\b",
    re.IGNORECASE,
)


def get_system_context() -> str:
    """Return local macOS context (time, day, battery) to ground the assistant."""
    now = datetime.datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    ctx = f"[System Context: {now} | OS: macOS]"
    try:
        res = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=1)
        if "InternalBattery" in res.stdout:
            for line in res.stdout.splitlines():
                if "InternalBattery" in line:
                    batt = line.split(";")[0].split("\t")[-1].strip()
                    status = line.split(";")[1].strip() if ";" in line else ""
                    ctx = f"[System Context: {now} | Battery: {batt} ({status}) | OS: macOS]"
                    break
    except Exception:
        pass
    return ctx


def response_token_limit(text: str) -> int:
    """Reserve longer generations for requests that explicitly need detail."""
    return 220 if DETAIL_REQUEST_PATTERN.search(text) else 48


class Brain:
    """A chat model behind a stream: local Ollama, or any OpenAI-compatible API.

    Note: on this machine the local models answer in ~0.1s warm, so a hosted
    model buys reply quality, not speech latency.
    """

    def __init__(self, model: str = "qwen3-coder:latest", host: str = "http://localhost:11434",
                 enabled: bool = True, api: str = "ollama", api_key: str = "",
                 vision_model: str = "qwen2.5vl:3b", context: int = 8192,
                 system_prompt: str = SYSTEM_PROMPT) -> None:
        self.model, self.host, self.enabled = model, host.rstrip("/"), enabled
        self.api, self.api_key = api, api_key
        self.vision_model = vision_model
        # qwen3-coder defaults to a 262k context (45 GB resident). Rocky only
        # ever sends a persona + one line, so 8k keeps it at ~19 GB.
        self.context = context
        self.checked = None
        self._response_lock = threading.Lock()
        self._active_response = None
        self.tools = default_registry
        self.system_prompt = system_prompt

    def set_persona(self, system_prompt: str) -> None:
        """Update system persona prompt and conversation history."""
        self.system_prompt = system_prompt
        if hasattr(self, 'history') and self.history:
            self.history[0] = {"role": "system", "content": system_prompt}
        else:
            self.history = [{"role": "system", "content": system_prompt}]

    def cancel(self) -> None:
        """Close the active text stream so an interrupted turn can finish."""
        with self._response_lock:
            response = self._active_response
        if response is not None:
            try:
                response.close()
            except OSError as e:
                print(f"[brain] could not close interrupted response: {e}", file=sys.stderr)

    def available(self) -> bool:
        if not self.enabled:
            return False
        if self.api in ("openai", "anthropic"):
            local = "localhost" in self.host or "127.0.0.1" in self.host
            self.checked = bool(self.api_key) or local
            return self.checked
        if self.checked is None:
            try:
                with urllib.request.urlopen(f"{self.host}/api/tags", timeout=2) as r:
                    models = [m["name"] for m in json.loads(r.read()).get("models", [])]
                self.checked = bool(models)
                if self.checked and self.model not in models:
                    print(f"[brain] {self.model} not pulled; have: {', '.join(models[:4])}",
                          file=sys.stderr)
            except Exception:  # noqa: BLE001
                self.checked = False
        return self.checked

    def _request(self, text: str):
        headers = {"Content-Type": "application/json"}
        token_limit = response_token_limit(text)
        # Initialize history if not already done
        if not hasattr(self, 'history') or not self.history:
            sys_prompt = f"{getattr(self, 'system_prompt', SYSTEM_PROMPT)}\n\n{get_system_context()}"
            self.history = [{"role": "system", "content": sys_prompt}]
        else:
            sys_prompt = f"{getattr(self, 'system_prompt', SYSTEM_PROMPT)}\n\n{get_system_context()}"
            self.history[0] = {"role": "system", "content": sys_prompt}
        
        if self.api == "openai":
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            body = json.dumps({
                "model": self.model,
                "messages": self.history,
                "stream": True,
                "max_tokens": token_limit,
                "temperature": 0.8,
            }).encode()
            return urllib.request.Request(f"{self.host}/chat/completions", data=body,
                                          headers=headers)
        body = json.dumps({
            "model": self.model,
            "messages": self.history,
            "tools": self.tools.to_ollama_tools(),
            "stream": True,
            "keep_alive": "30m",
            "options": {"num_predict": token_limit, "temperature": 0.8, "top_p": 0.9,
                        "num_ctx": self.context},
        }).encode()
        return urllib.request.Request(f"{self.host}/api/chat", data=body, headers=headers)

    def _vision_request(self, prompt: str, b64: str, stream: bool = True):
        headers = {"Content-Type": "application/json"}
        if self.api == "anthropic":
            headers["x-api-key"] = self.api_key
            headers["anthropic-version"] = "2023-06-01"
            body = {
                "model": self.vision_model,
                "max_tokens": 80,
                "system": VISION_PROMPT,
                "stream": True,
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64",
                                                 "media_type": "image/jpeg",
                                                 "data": b64}},
                    {"type": "text", "text": prompt}]}],
            }
            return urllib.request.Request(f"{self.host}/messages",
                                          data=json.dumps(body).encode(), headers=headers)
        if self.api == "openai":
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            body = {
                "model": self.vision_model,
                "stream": True,
                "max_tokens": 60,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": f"{VISION_PROMPT} {prompt}"},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
            }
            return urllib.request.Request(f"{self.host}/chat/completions",
                                          data=json.dumps(body).encode(), headers=headers)
        body = {
            "model": self.vision_model,
            "messages": [{"role": "user", "content": f"{VISION_PROMPT} {prompt}",
                          "images": [b64]}],
            "stream": stream,
            "options": {"num_predict": 60, "temperature": 0.1},
        }
        return urllib.request.Request(f"{self.host}/api/chat",
                                      data=json.dumps(body).encode(), headers=headers)

    def _deltas(self, resp):
        """Yield text tokens or parsed tool_call tags from the HTTP response."""
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line:
                continue
            if self.api in ("openai", "anthropic"):
                if not line.startswith("data:"):
                    continue
                line = line[5:].strip()
                if line == "[DONE]":
                    break
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if self.api == "anthropic":
                    delta = (obj.get("delta", {}).get("text", "")
                             if obj.get("type") == "content_block_delta" else "")
                else:
                    try:
                        choice = obj["choices"][0]
                        delta = choice.get("delta", {}).get("content") or ""
                        for tc in choice.get("delta", {}).get("tool_calls") or []:
                            fn = tc.get("function", {})
                            tname = fn.get("name")
                            targs = fn.get("arguments", "{}")
                            if tname:
                                args_str = targs if isinstance(targs, str) else json.dumps(targs)
                                yield f'<tool_call name="{tname}" args=\'{args_str}\' />'
                    except (KeyError, IndexError):
                        delta = ""
            else:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message", {})
                delta = msg.get("content", "")
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    tname = fn.get("name")
                    targs = fn.get("arguments", {})
                    if tname:
                        args_str = json.dumps(targs) if isinstance(targs, dict) else str(targs)
                        yield f'<tool_call name="{tname}" args=\'{args_str}\' />'
                if obj.get("done"):
                    break
            if delta:
                yield delta

    def stream(self, text: str, cancel_event: threading.Event | None = None):
        """Yield content deltas as they arrive."""
        if (cancel_event is not None and cancel_event.is_set()) or not self.available():
            return
        
        # Initialize history if not already done
        if not hasattr(self, 'history') or not self.history:
            sys_prompt = f"{getattr(self, 'system_prompt', SYSTEM_PROMPT)}\n\n{get_system_context()}"
            self.history = [{"role": "system", "content": sys_prompt}]
        else:
            sys_prompt = f"{getattr(self, 'system_prompt', SYSTEM_PROMPT)}\n\n{get_system_context()}"
            self.history[0] = {"role": "system", "content": sys_prompt}
        self.history.append({"role": "user", "content": text})
        
        pattern = re.compile(r'<tool_call\s+name=["\']([^"\']*)["\']\s+args=["\'](.*?)["\']\s*/>')
        max_tool_turns = 3
        turn = 0
        
        while turn < max_tool_turns:
            turn += 1
            response = None
            tool_called = False
            unyielded_buffer = ""
            full_reply = ""
            
            try:
                response = urllib.request.urlopen(self._request(text), timeout=120)
                with self._response_lock:
                    self._active_response = response
                if cancel_event is not None and cancel_event.is_set():
                    return
                
                for delta in self._deltas(response):
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    
                    unyielded_buffer += delta
                    matches = list(pattern.finditer(unyielded_buffer))
                    if matches:
                        first_match = matches[0]
                        pre_tool_text = unyielded_buffer[:first_match.start()]
                        if pre_tool_text:
                            yield pre_tool_text
                            full_reply += pre_tool_text
                        
                        tool_calls = []
                        for match in matches:
                            tool_name = match.group(1)
                            args_str = match.group(2)
                            try:
                                args = json.loads(args_str) if args_str else {}
                            except json.JSONDecodeError:
                                args = {}
                            tool_calls.append({"name": tool_name, "args": args})
                        
                        tool_results = []
                        for tool_call in tool_calls:
                            res = self.tools.call(tool_call["name"], tool_call["args"])
                            tool_results.append({"tool_call": tool_call, "result": res})
                        
                        for tool_call in tool_calls:
                            tc_text = f'<tool_call name="{tool_call["name"]}" args=\'{json.dumps(tool_call["args"])}\' />'
                            self.history.append({"role": "assistant", "content": tc_text})
                        
                        for tr in tool_results:
                            res_content = tr["result"].content if hasattr(tr["result"], 'content') else str(tr["result"])
                            tool_name = tr["tool_call"]["name"]
                            prompt_instruction = (
                                f"[Tool '{tool_name}' result: {res_content}]\n"
                                f"Answer the user's question directly and concisely in your character's voice using this result."
                            )
                            self.history.append({"role": "tool", "content": prompt_instruction})
                        
                        tool_called = True
                        unyielded_buffer = ""
                        break  # Break out of delta stream to request continuation with tool results
                    else:
                        if unyielded_buffer and '<' not in unyielded_buffer:
                            yield unyielded_buffer
                            full_reply += unyielded_buffer
                            unyielded_buffer = ""
                
                if unyielded_buffer and not tool_called:
                    yield unyielded_buffer
                    full_reply += unyielded_buffer
                    unyielded_buffer = ""
                
                if not tool_called:
                    if full_reply:
                        self.history.append({"role": "assistant", "content": full_reply})
                    break
                    
            except (urllib.error.URLError, TimeoutError, ValueError, OSError,
                    http.client.HTTPException) as e:
                if cancel_event is None or not cancel_event.is_set():
                    print(f"[brain] {e}", file=sys.stderr)
                break
            finally:
                with self._response_lock:
                    if self._active_response is response:
                        self._active_response = None
                if response is not None:
                    response.close()
        
        # Keep history bounded (system prompt + last 18 messages)
        if hasattr(self, 'history') and len(self.history) > 20:
            self.history = [self.history[0]] + self.history[-19:]

    def vision_stream(self, prompt: str = "Describe the scene.", jpeg: bytes = b""):
        """Stream a description of one camera frame."""
        if not self.available() or not jpeg:
            return
        b64 = base64.b64encode(jpeg).decode()
        try:
            if self.api == "ollama":
                # Local vision models drop their first character when streamed,
                # and one short sentence gains nothing from it.
                with urllib.request.urlopen(self._vision_request(prompt, b64, stream=False),
                                            timeout=180) as r:
                    text = json.loads(r.read()).get("message", {}).get("content", "")
                if text.strip():
                    yield text.strip()
                return
            with urllib.request.urlopen(self._vision_request(prompt, b64), timeout=180) as r:
                yield from self._deltas(r)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read()).get("error", "")
            except Exception:  # noqa: BLE001
                pass
            print(f"[vision] HTTP {e.code}: {detail or e.reason}", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"[vision] {e}", file=sys.stderr)

    def vision(self, prompt: str, jpeg: bytes) -> str:
        return "".join(self.vision_stream(prompt, jpeg)).strip()

    def reply(self, text: str) -> str:
        return "".join(self.stream(text)).strip()

    def warm(self) -> None:
        """Load the model into memory so the first turn is not slower."""
        try:
            for _ in self.stream("hi"):
                break
        except Exception:  # noqa: BLE001
            pass


def split_sentences(text: str, limit: int = 150):
    """Sentence-ish chunks, each short enough to synthesize in one breath."""
    parts = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    out = []
    for p in parts:
        while len(p) > limit:
            cut = p.rfind(" ", 0, limit)
            cut = cut if cut > 40 else limit
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out or [text]


def sentence_stream(brain: Brain, text: str,
                    cancel_event: threading.Event | None = None):
    """Turn streamed LLM deltas into sentences and early opener clauses.

    Splits on sentence endings (.!?), or on early clause boundaries (,;:—) on the
    opening phrase so TTS can start in ~300ms while remaining tokens are still
    generating.
    """
    buf = ""
    is_first = True

    for delta in brain.stream(text, cancel_event=cancel_event):
        if cancel_event is not None and cancel_event.is_set():
            return
        buf += delta

        while True:
            # 1. Full sentence boundary
            m_sent = re.search(r"[.!?]+(?:\s+|$)", buf)
            if m_sent:
                end = m_sent.end()
                chunk = buf[:end].strip()
                if len(chunk) >= 6 or not is_first:
                    buf = buf[end:]
                    is_first = False
                    if chunk:
                        yield chunk
                    continue

            # 2. Early clause boundary for chunk 0
            if is_first:
                m_clause = re.search(r"[,;:\u2014]+(?:\s+)", buf)
                if m_clause:
                    clause = buf[:m_clause.start()].strip() + m_clause.group(0).rstrip()
                    rest = buf[m_clause.end():]
                    # Ensure enough characters to sound natural, avoid splitting numbers/dates or questions
                    if len(clause) >= 10 and len(rest.strip()) >= 10:
                        if not (clause[-1].isdigit() and rest.strip()[0].isdigit()):
                            if not rest.strip().startswith("question?"):
                                buf = rest
                                is_first = False
                                yield clause
                                continue
            break

    if buf.strip():
        yield buf.strip()
