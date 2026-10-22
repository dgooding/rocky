#!/usr/bin/env python3
"""
Talk to Rocky - a little local web app for rocky-tts (Project Hail Mary).

Runs on stdlib only. Reuses rocky_say.py for the Rocky-speak transform and
the persistent XTTS v2 server (spawned on demand, ~17s model load).

    python3 app.py            # http://127.0.0.1:8765
    python3 app.py --port 9000
"""
import argparse
import json
import os
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "rocky-tts"))
import rocky_say as rocky  # noqa: E402  (stdlib-only module imports)

_loading = threading.Lock()


def tts_ready():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{rocky.SERVER_PORT}/health", timeout=1)
        return True
    except Exception:
        return False


def warm_model():
    """Load XTTS in the background; server_start() polls until healthy."""
    if tts_ready() or _loading.locked():
        return
    with _loading:
        try:
            rocky.server_start()
        except Exception as e:  # noqa: BLE001
            print(f"warm_model failed: {e}", file=sys.stderr)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Talk to Rocky</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root { --bg:#0b0f14; --fg:#d7e3ee; --dim:#5d7285; --rocky:#7fd4c1; --user:#8fb6ff; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:15px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;
         display:flex; flex-direction:column; height:100vh; }
  header { display:flex; align-items:center; gap:12px; padding:14px 18px;
           border-bottom:1px solid #16222d; }
  h1 { font-size:15px; margin:0; font-weight:600; letter-spacing:.04em; }
  #pill { font-size:12px; padding:2px 9px; border-radius:999px; border:1px solid var(--dim); color:var(--dim); }
  #pill.ready { color:var(--rocky); border-color:var(--rocky); }
  #pill.warm { color:#e0b355; border-color:#e0b355; }
  #log { flex:1; overflow-y:auto; padding:18px; display:flex; flex-direction:column; gap:14px; }
  .msg { max-width:min(680px,88%); white-space:pre-wrap; word-wrap:break-word; }
  .me { align-self:flex-end; color:var(--user); text-align:right; }
  .rocky { align-self:flex-start; color:var(--rocky); }
  .said { color:var(--dim); font-size:13px; display:block; margin-top:3px; }
  .err { align-self:center; color:#ff8f8f; font-size:13px; }
  footer { display:flex; gap:10px; padding:14px 18px; border-top:1px solid #16222d; }
  input { flex:1; background:#111a22; border:1px solid #22323f; color:var(--fg);
          padding:11px 13px; border-radius:8px; font:inherit; outline:none; }
  input:focus { border-color:var(--rocky); }
  button { background:#17303a; color:var(--fg); border:1px solid #2b4a56; padding:11px 16px;
           border-radius:8px; font:inherit; cursor:pointer; }
  button:disabled { opacity:.45; cursor:default; }
  button.rec { background:#5c1f28; border-color:#a33; color:#ffd9d9; }
</style></head><body>
<header><h1>ROCKY</h1><span id="pill">checking&hellip;</span></header>
<div id="log"></div>
<footer>
  <input id="box" placeholder="say something to Rocky&hellip;" autocomplete="off" autofocus>
  <button id="mic" title="speak instead of typing">&#127908;</button>
  <button id="send">Send</button>
</footer>
<script>
const log = document.getElementById('log'), box = document.getElementById('box');
const send = document.getElementById('send'), mic = document.getElementById('mic');
const pill = document.getElementById('pill');
let busy = false;

function add(cls, text, said) {
  const d = document.createElement('div');
  d.className = 'msg ' + cls;
  d.textContent = text;
  if (said) { const s = document.createElement('span'); s.className='said'; s.textContent='said: '+said; d.appendChild(s); }
  log.appendChild(d); log.scrollTop = log.scrollHeight;
  return d;
}
function setPill(state, label) { pill.className = state; pill.textContent = label; }

async function status() {
  try {
    const s = await (await fetch('/status')).json();
    if (s.ready) setPill('ready', 'ready \\u00b7 ' + s.voice);
    else if (s.loading) setPill('warm', 'loading model\\u2026');
    else setPill('', 'asleep - tap to wake');
    return s;
  } catch { setPill('', 'offline'); return {ready:false}; }
}
async function ensureAwake() {
  const s = await status();
  if (s.ready) return true;
  setPill('warm', 'loading model\\u2026');
  await fetch('/warm', {method:'POST'});
  for (let i = 0; i < 120; i++) {
    await new Promise(r => setTimeout(r, 2000));
    if ((await status()).ready) return true;
  }
  return false;
}
async function say() {
  const text = box.value.trim();
  if (!text || busy) return;
  box.value = ''; add('me', text);
  busy = true; send.disabled = mic.disabled = true;
  const thinking = add('rocky', '\\u2026');
  try {
    const r = await fetch('/say', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({text})
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      thinking.remove();
      if (r.status === 503) { thinking.remove(); if (await ensureAwake()) return sayWith(text); }
      add('err', e.error || ('error ' + r.status));
      return;
    }
    const said = decodeURIComponent(r.headers.get('X-Rocky-Said') || '');
    const blob = await r.blob();
    thinking.remove();
    add('rocky', said || text, said && said !== text ? text : null);
    new Audio(URL.createObjectURL(blob)).play();
  } catch (e) {
    thinking.remove(); add('err', 'request failed: ' + e.message);
  } finally { busy = false; send.disabled = mic.disabled = false; box.focus(); }
}
async function sayWith(text) { box.value = text; return say(); }

send.onclick = say;
box.onkeydown = e => { if (e.key === 'Enter') say(); };
pill.onclick = () => ensureAwake();

// Optional: speak to it via the browser's speech recognition.
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SR) {
  const rec = new SR();
  rec.lang = 'en-US'; rec.interimResults = false;
  rec.onresult = e => { box.value = e.results[0][0].transcript; say(); };
  rec.onend = () => mic.classList.remove('rec');
  mic.onclick = () => { mic.classList.add('rec'); rec.start(); };
} else {
  mic.disabled = true; mic.title = 'speech recognition needs Chrome or Safari';
}

status().then(s => { if (!s.ready) ensureAwake(); });
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "rocky-app"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif path == "/status":
            ready = tts_ready()
            self._json(200, {
                "ready": ready,
                "loading": _loading.locked(),
                "voice": "rocky" if ready else None,
            })
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(n).decode() or "{}"
        try:
            data = json.loads(raw_body)
        except Exception:
            data = {}

        if self.path == "/warm":
            threading.Thread(target=warm_model, daemon=True).start()
            self._json(200, {"loading": True})
            return

        if self.path != "/say":
            self._json(404, {"error": "not found"})
            return

        text = (data.get("text") or "").strip()
        if not text:
            self._json(400, {"error": "empty text"})
            return

        spoken = text if data.get("raw") else rocky.rocky_transform(text)

        if not tts_ready():
            threading.Thread(target=warm_model, daemon=True).start()
            self._json(503, {"error": "voice model not loaded yet", "spoken": spoken})
            return

        wav = rocky.generate_via_server(spoken)
        if not wav:
            self._json(502, {"error": "synthesis failed - check rocky-tts/logs/rocky_server.log"})
            return

        # Header carries the Rocky-speak so the UI can show what was actually said.
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav)))
        self.send_header("X-Rocky-Said", urllib.request.quote(spoken, safe=""))
        self.send_header("X-Rocky-Input", urllib.request.quote(text, safe=""))
        self.end_headers()
        self.wfile.write(wav)


def main():
    ap = argparse.ArgumentParser(description="Talk to Rocky")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--warm", action="store_true", help="start loading the voice model immediately")
    args = ap.parse_args()

    print(f"Talk to Rocky -> http://{args.host}:{args.port}")
    print(f"voice server  -> http://127.0.0.1:{rocky.SERVER_PORT} (XTTS v2)")
    if args.warm:
        threading.Thread(target=warm_model, daemon=True).start()

    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
