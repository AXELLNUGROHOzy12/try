#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import ssl 
ssl._create_default_https_context = ssl._create_unverified_context
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request
import urllib.error
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DATA_DIR bisa diarahkan ke Railway Volume (mis. /data) supaya config,
# daftar user, token, dll tidak hilang tiap kali redeploy.
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
USERS_FILE = os.path.join(DATA_DIR, "user.json")
TOKEN_FILE = os.path.join(DATA_DIR, "token.json")

# Kalau DATA_DIR custom (volume) dan file belum ada di sana, salin dari
# versi bawaan project (kalau ada) sekali di awal biar config awal tidak hilang.
for _fname, _dst in (("config.json", CONFIG_FILE), ("user.json", USERS_FILE), ("token.json", TOKEN_FILE)):
    _seed = os.path.join(BASE_DIR, _fname)
    if not os.path.exists(_dst) and os.path.exists(_seed) and _seed != _dst:
        import shutil
        shutil.copyfile(_seed, _dst)
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
CHATGPT_MODEL = "gpt-4o-mini"
CHATGPT_API_BASE = "https://api.openai.com/v1/chat/completions"

BUILTIN_AI = ["gemini", "chatgpt"]

# ── Rate limit: berlaku PER-IP, terlepas dari API key valid atau tidak ──
# Ini jaga-jaga kalau key bocor / di-share, orang tetap nggak bisa spam.
RATE_LIMIT_MAX = 20      # maksimal request
RATE_LIMIT_WINDOW = 60   # per 60 detik
_rate_buckets = defaultdict(deque)

def is_rate_limited(ip):
    now = time.time()
    bucket = _rate_buckets[ip]
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_MAX:
        return True
    bucket.append(now)
    return False

def get_all_providers(cfg):
    """Built-in + semua custom endpoint yang udah ditambahkan."""
    custom = list(cfg.get("endpoints", {}).keys())
    return BUILTIN_AI + custom

DEFAULT_CONFIG = {
    "nama_ai": "Nova",
    "nama_user": "Kamu",
    "kepribadian": "Jawab singkat, ramah, dan gaul bro.",
    "kode_akses": "SXIELD1",
    "owner_wa": "628772703519",
    "port": 8000
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def load_users():
    if not os.path.exists(USERS_FILE):
        # Bikin akun default admin kalau belum ada (admin / 123)
        default_users = {"admin": {"password": "123", "is_admin": True}}
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_users, f, indent=2)
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(users_data):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users_data, f, indent=2)

def load_tokens():
    """Baca token.json — {username: token}. Buat kosong kalau belum ada."""
    if not os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "w") as f:
            json.dump({}, f, indent=2)
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)

def save_tokens(tokens_data):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens_data, f, indent=2)

config = load_config()

# ── API Key ─────────────────────────────────────────────
# Prioritas: env var API_KEY (disarankan di Railway, tidak ikut ke-commit)
# selalu jadi "master key" (nama tampilan "env"), dipakai server-ke-server
# oleh wa.js. Selain itu, config.json["api_keys"] nyimpen banyak key
# ber-nama, masing-masing dengan hitungan pemakaian & waktu terakhir
# dipakai — biar per-client bisa dicabut satu-satu tanpa ganggu yang lain.
#
# Struktur config["api_keys"]:
#   { "<key>": {"name": "web-widget", "created": <ts>, "requests": 0, "last_used": <ts|None>} }
def ensure_api_keys(cfg):
    if "api_keys" not in cfg or not isinstance(cfg["api_keys"], dict):
        cfg["api_keys"] = {}
    # Migrasi dari format lama (single "api_key" string)
    old = cfg.pop("api_key", None)
    if old and old not in cfg["api_keys"]:
        cfg["api_keys"][old] = {"name": "default", "created": time.time(), "requests": 0, "last_used": None}
    # Kalau belum ada key sama sekali dan env var juga kosong, bikinin satu
    # biar client pertama (web widget) tetap bisa login.
    if not cfg["api_keys"] and not os.environ.get("API_KEY", "").strip():
        new_key = secrets.token_hex(24)
        cfg["api_keys"][new_key] = {"name": "default", "created": time.time(), "requests": 0, "last_used": None}
        print(f"⚠️  Belum ada API key — key baru digenerate (nama: default): {new_key}")
        print("    Lihat lagi lewat: /apikey {kode_akses} list")
    save_config(cfg)
    return cfg["api_keys"]

ensure_api_keys(config)
ENV_MASTER_KEY = os.environ.get("API_KEY", "").strip()

def check_api_key(handler):
    """Validasi header X-Api-Key. Kalau cocok, catat pemakaian & balikin
    nama key-nya (string). Kalau tidak valid, balikin None."""
    sent = handler.headers.get("X-Api-Key", "")
    if not sent:
        return None
    if ENV_MASTER_KEY and secrets.compare_digest(sent, ENV_MASTER_KEY):
        return "env-master"
    for key, meta in config.get("api_keys", {}).items():
        if secrets.compare_digest(sent, key):
            meta["requests"] = meta.get("requests", 0) + 1
            meta["last_used"] = time.time()
            save_config(config)
            return meta.get("name", "unnamed")
    return None

chat_sessions = {}
session_ai = {}   # session_id → provider aktif, default "gemini"
global_ai   = config.get("global_ai") or None  # persist across restarts
# Muat semua token admin dari file ke memory saat startup
_stored_tokens = load_tokens()
admin_tokens = set(_stored_tokens.values())  # set of token strings untuk lookup cepat

def build_system_prompt(cfg):
    return f"Nama lu adalah {cfg.get('nama_ai', 'AI')}. {cfg.get('kepribadian', '')} Jangan nyebut lu AI buatan pihak lain."

# ── Gemini ──────────────────────────────────────────────
def call_gemini(messages, cfg):
    api_key = os.environ.get("GEMINI_API_KEY") or cfg.get("gemini_api_key", "")
    if not api_key:
        return None, "GEMINI_API_KEY tidak ditemukan. Pakai /change {kode} gemini {key}"

    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["text"]}]})

    url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={urllib.parse.quote(api_key, safe='')}"
    payload = {
        "system_instruction": {"parts": [{"text": build_system_prompt(cfg)}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.7}
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return result["candidates"][0]["content"]["parts"][0]["text"].strip(), None
    except urllib.error.HTTPError as e:
        return None, f"Gemini error {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)

# ── ChatGPT ─────────────────────────────────────────────
def call_chatgpt(messages, cfg):
    api_key = os.environ.get("OPENAI_API_KEY") or cfg.get("chatgpt_api_key", "")
    if not api_key:
        return None, "OPENAI_API_KEY tidak ditemukan. Pakai /change {kode} chatgpt {key}"

    oai_messages = [{"role": "system", "content": build_system_prompt(cfg)}]
    for m in messages:
        role = "user" if m["role"] == "user" else "assistant"
        oai_messages.append({"role": role, "content": m["text"]})

    payload = {"model": CHATGPT_MODEL, "messages": oai_messages, "temperature": 0.7}
    req = urllib.request.Request(CHATGPT_API_BASE, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return result["choices"][0]["message"]["content"].strip(), None
    except urllib.error.HTTPError as e:
        return None, f"ChatGPT error {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)

# ── Cari teks dari respons JSON secara rekursif ──────────
_TIMESTAMP_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')

def _is_junk(s):
    """Abaikan timestamp ISO dan string sangat pendek."""
    return bool(_TIMESTAMP_RE.match(s)) or len(s) < 2

def _extract_text(obj, depth=0):
    """Cari teks respons di dalam JSON secara rekursif."""
    if depth > 6:
        return None
    if isinstance(obj, str):
        s = obj.strip()
        return None if _is_junk(s) else s
    if isinstance(obj, dict):
        # Prioritaskan key umum — termasuk "data" untuk wrapper siputzx-style
        for key in ("response", "text", "content", "message", "answer",
                    "reply", "output", "result", "generated_text", "data"):
            if key in obj:
                val = _extract_text(obj[key], depth + 1)
                if val:
                    return val
        # Fallback: cari nilai string terpanjang dari sisa key
        best = None
        for k, v in obj.items():
            if k in ("status", "ok", "success", "timestamp", "time", "code", "error"):
                continue
            val = _extract_text(v, depth + 1)
            if val and (best is None or len(val) > len(best)):
                best = val
        return best
    if isinstance(obj, list) and obj:
        best = None
        for item in obj:
            val = _extract_text(item, depth + 1)
            if val and (best is None or len(val) > len(best)):
                best = val
        return best
    return None

# ── Custom endpoint ───────────────────────────────────────
def call_custom(messages, cfg, name):
    endpoint = cfg.get("endpoints", {}).get(name)
    if not endpoint:
        return None, f"Endpoint '{name}' tidak ditemukan."
    api_key = cfg.get(f"{name}_api_key", "")

    # Ambil pesan terakhir dari user sebagai prompt
    last_user = next((m["text"] for m in reversed(messages) if m["role"] == "user"), "")

    try:
        # ── Mode GET: URL mengandung {prompt} ────────────────
        if "{prompt}" in endpoint:
            encoded = urllib.parse.quote(last_user, safe="")
            url = endpoint.replace("{prompt}", encoded)
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/125.0.0.0 Safari/537.36")
            req.add_header("Accept", "application/json, text/plain, */*")
            req.add_header("Accept-Language", "en-US,en;q=0.9")
            # Referer otomatis dari domain endpoint supaya lolos Cloudflare
            parsed = urllib.parse.urlparse(url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            req.add_header("Referer", origin + "/")
            req.add_header("Origin", origin)
            if api_key:
                req.add_header("Authorization", f"Bearer {api_key}")
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            # Coba parse JSON, fallback ke raw text
            try:
                result = json.loads(raw)
                text = _extract_text(result)
                if text:
                    return text, None
            except json.JSONDecodeError:
                if raw.strip():
                    return raw.strip(), None
            return None, f"Format respons tidak dikenali: {raw[:200]}"

        # ── Mode POST: OpenAI-compatible ─────────────────────
        oai_messages = [{"role": "system", "content": build_system_prompt(cfg)}]
        for m in messages:
            role = "user" if m["role"] == "user" else "assistant"
            oai_messages.append({"role": role, "content": m["text"]})

        payload = {"messages": oai_messages, "temperature": 0.7}
        # Sertakan model jika dikonfigurasi (banyak API wajib field ini)
        model = cfg.get(f"{name}_model")
        if model:
            payload["model"] = model
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(),
                                     method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8", errors="ignore"))
        if "choices" in result:
            choice = result["choices"][0]
            # Support message.content (object) atau text (string langsung)
            msg_obj = choice.get("message", {})
            content = msg_obj.get("content") or choice.get("text")
            if content:
                return str(content).strip(), None
        text = _extract_text(result)
        if text:
            return text, None
        return None, f"Format respons tidak dikenali: {str(result)[:200]}"

    except urllib.error.HTTPError as e:
        return None, f"{name} error {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)

# ── Router ───────────────────────────────────────────────
def call_ai(messages, cfg, provider="gemini"):
    if provider == "chatgpt":
        return call_chatgpt(messages, cfg)
    if provider == "gemini":
        return call_gemini(messages, cfg)
    # Custom endpoint
    return call_custom(messages, cfg, provider)

class Handler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Code, X-Api-Key")
        self.end_headers()

    def _serve_file(self, filepath, content_type):
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "File tidak ditemukan"}).encode())

    def do_OPTIONS(self):
        self._set_headers(204)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._serve_file("static/index.html", "text/html; charset=utf-8")
        elif path == "/qr":
            self._serve_file("static/qr.html", "text/html; charset=utf-8")
        elif path == "/admin":
            self._serve_file("static/admin.html", "text/html; charset=utf-8")
        elif path == "/qr-data":
            self._serve_qr_data()
        elif path == "/qr-image":
            self._serve_file(os.path.join(DATA_DIR, "qr_current.png"), "image/png")
        elif path.startswith("/static/"):
            fname = path.lstrip("/")
            ext = fname.rsplit(".", 1)[-1] if "." in fname else ""
            mime = {"css": "text/css", "js": "application/javascript",
                    "png": "image/png", "jpg": "image/jpeg",
                    "svg": "image/svg+xml", "ico": "image/x-icon"}.get(ext, "text/plain")
            self._serve_file(fname, mime)
        elif path == "/status":
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "status": "ok",
                "config": {
                    "nama_ai":  config.get("nama_ai", "Nova AI"),
                    "owner_wa": config.get("owner_wa", "")
                }
            }).encode())
        else:
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ok"}).encode())

    def _serve_qr_data(self):
        try:
            with open(os.path.join(DATA_DIR, "qr_current.txt"), "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content == "connected":
                result = {"status": "connected"}
            elif content == "loggedout":
                result = {"status": "loggedout"}
            else:
                result = {"status": "waiting", "qr": content}
        except FileNotFoundError:
            result = {"status": "loading"}
        self._set_headers(200)
        self.wfile.write(json.dumps(result).encode())

    def do_POST(self):
        if self.path == "/login":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            u = data.get("username", "")
            p = data.get("password", "")
            session_id = data.get("session_id", "")
            users = load_users()
            if u in users and users[u]["password"] == p:
                is_admin = users[u].get("is_admin", False)
                token = None
                if is_admin:
                    tokens_data = load_tokens()
                    if u in tokens_data:
                        # Pakai token lama yang udah tersimpan
                        token = tokens_data[u]
                    else:
                        # Generate token baru dan simpan ke token.json
                        token = secrets.token_hex(32)
                        tokens_data[u] = token
                        save_tokens(tokens_data)
                    admin_tokens.add(token)
                resp = {"status": "ok", "is_admin": is_admin}
                if token:
                    resp["admin_token"] = token
                self._set_headers(200)
                self.wfile.write(json.dumps(resp).encode())
            else:
                self._set_headers(401)
                self.wfile.write(json.dumps({"error": "Login gagal"}).encode())

        elif self.path == "/chat":
            global config, global_ai
            client_ip = self.client_address[0]

            if is_rate_limited(client_ip):
                self._set_headers(429)
                self.wfile.write(json.dumps({"error": "Terlalu banyak request, coba lagi sebentar."}).encode())
                return

            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            msg = data.get("message", "").strip()
            session_id = data.get("session_id", "default")

            # Command admin (/add, /delete, /change, /apikey) dilindungi oleh
            # kode_akses sendiri-sendiri, jadi tetap bisa dipanggil walau
            # X-Api-Key hilang/lupa — dipakai buat recovery. Selain itu
            # (chat biasa & /ai) wajib X-Api-Key valid.
            ADMIN_CMD_PREFIXES = ("/add ", "/delete ", "/change ", "/apikey ")
            if not msg.startswith(ADMIN_CMD_PREFIXES):
                if check_api_key(self) is None:
                    self._set_headers(401)
                    self.wfile.write(json.dumps({"error": "API key tidak valid. Sertakan header X-Api-Key."}).encode())
                    return

            # ── /apikey {kode_akses} list|new {nama}|revoke {nama} — kelola API key ──
            if msg.startswith("/apikey "):
                parts = msg.split(" ", 3)
                if len(parts) < 3:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({
                        "error": "Format:\n/apikey {kode_akses} list\n"
                                 "/apikey {kode_akses} new {nama}\n"
                                 "/apikey {kode_akses} revoke {nama}"
                    }).encode())
                    return
                kode_input, action = parts[1], parts[2].strip().lower()
                if kode_input != config.get("kode_akses", ""):
                    self._set_headers(403)
                    self.wfile.write(json.dumps({"error": "Kode akses salah."}).encode())
                    return

                if action == "list":
                    lines = []
                    if ENV_MASTER_KEY:
                        lines.append("• env-master (dari Variables Railway, tidak bisa direvoke lewat chat)")
                    for key, meta in config.get("api_keys", {}).items():
                        last = meta.get("last_used")
                        last_str = time.strftime("%d/%m %H:%M", time.localtime(last)) if last else "belum pernah"
                        lines.append(f"• {meta.get('name')} — {meta.get('requests', 0)}x pakai, terakhir {last_str}\n  {key}")
                    reply = "🔑 Daftar API key:\n\n" + ("\n".join(lines) if lines else "(kosong)")
                    self._set_headers(200)
                    self.wfile.write(json.dumps({"reply": reply}).encode())
                    return

                if action == "new":
                    if len(parts) < 4 or not parts[3].strip():
                        self._set_headers(400)
                        self.wfile.write(json.dumps({"error": "Format: /apikey {kode_akses} new {nama}"}).encode())
                        return
                    nama = parts[3].strip()
                    new_key = secrets.token_hex(24)
                    config.setdefault("api_keys", {})[new_key] = {
                        "name": nama, "created": time.time(), "requests": 0, "last_used": None
                    }
                    save_config(config)
                    self._set_headers(200)
                    self.wfile.write(json.dumps({
                        "reply": f"✅ Key baru untuk '{nama}' berhasil dibuat:\n{new_key}\n\nSimpan baik-baik, key cuma ditampilkan sekali di sini (tapi bisa dicek ulang lewat 'list')."
                    }).encode())
                    return

                if action == "revoke":
                    if len(parts) < 4 or not parts[3].strip():
                        self._set_headers(400)
                        self.wfile.write(json.dumps({"error": "Format: /apikey {kode_akses} revoke {nama}"}).encode())
                        return
                    target = parts[3].strip()
                    keys = config.get("api_keys", {})
                    to_remove = [k for k, m in keys.items() if m.get("name") == target or k == target]
                    if not to_remove:
                        self._set_headers(404)
                        self.wfile.write(json.dumps({"error": f"Key/nama '{target}' tidak ditemukan."}).encode())
                        return
                    for k in to_remove:
                        del keys[k]
                    save_config(config)
                    self._set_headers(200)
                    self.wfile.write(json.dumps({
                        "reply": f"🗑️ {len(to_remove)} key untuk '{target}' dicabut. Client yang pakai key itu langsung ke-block."
                    }).encode())
                    return

                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Aksi tidak dikenal. Pakai 'list', 'new', atau 'revoke'."}).encode())
                return


            # ── /ai {provider} — ganti AI untuk sesi ini ──
            if msg.startswith("/ai "):
                provider = msg.split(" ", 1)[1].strip().lower()
                all_providers = get_all_providers(config)
                if provider not in all_providers:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({
                        "error": f"AI '{provider}' tidak dikenal. Pilihan: {', '.join(all_providers)}"
                    }).encode())
                    return
                # Kalau global_ai aktif, session_ai tidak berpengaruh — beri tahu user
                if global_ai:
                    self._set_headers(200)
                    labels = {"gemini": "Gemini 2.5 Flash", "chatgpt": "ChatGPT (GPT-4o mini)"}
                    label = labels.get(global_ai, global_ai)
                    self.wfile.write(json.dumps({
                        "reply": f"⚠️ AI global sedang aktif: *{label}*. Hanya owner yang bisa mengganti."
                    }).encode())
                    return
                session_ai[session_id] = provider
                labels = {"gemini": "Gemini 2.5 Flash", "chatgpt": "ChatGPT (GPT-4o mini)"}
                label = labels.get(provider, provider)
                self._set_headers(200)
                self.wfile.write(json.dumps({"reply": f"🤖 AI diganti ke {label}!"}).encode())
                return

            # ── /add {kode} {nama} {endpoint} — tambah custom endpoint ──
            if msg.startswith("/add "):
                parts = msg.split(" ", 3)
                if len(parts) < 4:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({
                        "error": "Format: /add {kode_akses} {nama} {endpoint_url}\nContoh: /add SXIELD1 mistral https://api.mistral.ai/v1/chat/completions"
                    }).encode())
                    return
                kode_input, nama, endpoint_url = parts[1], parts[2].lower(), parts[3].strip()
                if kode_input != config.get("kode_akses", ""):
                    self._set_headers(403)
                    self.wfile.write(json.dumps({"error": "Kode akses salah."}).encode())
                    return
                if nama in BUILTIN_AI:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": f"'{nama}' adalah nama built-in, pakai nama lain."}).encode())
                    return
                if "endpoints" not in config:
                    config["endpoints"] = {}
                config["endpoints"][nama] = endpoint_url
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "reply": f"✅ Endpoint '{nama}' ditambahkan!\nGunakan: /ai {nama}\nKalau butuh API key: /change {config.get('kode_akses')} {nama} {{api_key}}"
                }).encode())
                return

            # ── /delete {kode} {nama} — hapus custom endpoint ──
            if msg.startswith("/delete "):
                parts = msg.split(" ", 2)
                if len(parts) < 3:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({
                        "error": "Format: /delete {kode_akses} {nama}\nContoh: /delete SXIELD1 mistral"
                    }).encode())
                    return
                kode_input, nama = parts[1], parts[2].strip().lower()
                if kode_input != config.get("kode_akses", ""):
                    self._set_headers(403)
                    self.wfile.write(json.dumps({"error": "Kode akses salah."}).encode())
                    return
                if nama in BUILTIN_AI:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": f"'{nama}' adalah built-in, tidak bisa dihapus."}).encode())
                    return
                endpoints = config.get("endpoints", {})
                if nama not in endpoints:
                    self._set_headers(404)
                    self.wfile.write(json.dumps({"error": f"Endpoint '{nama}' tidak ditemukan."}).encode())
                    return
                del endpoints[nama]
                config.pop(f"{nama}_api_key", None)
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                # Reset sesi yang pakai provider ini ke gemini
                for sid, prov in list(session_ai.items()):
                    if prov == nama:
                        session_ai[sid] = "gemini"
                self._set_headers(200)
                self.wfile.write(json.dumps({"reply": f"🗑️ Endpoint '{nama}' berhasil dihapus."}).encode())
                return

            # ── /change {kode} {provider} {key} — ganti API key ──
            if msg.startswith("/change "):
                parts = msg.split(" ", 3)
                if len(parts) < 4:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({
                        "error": "Format: /change {kode_akses} {provider} {api_key}\nContoh: /change SXIELD1 gemini AQ.xxx\n        /change SXIELD1 mistral sk-xxx"
                    }).encode())
                    return
                kode_input, provider, new_key = parts[1], parts[2].lower(), parts[3].strip()
                if kode_input != config.get("kode_akses", ""):
                    self._set_headers(403)
                    self.wfile.write(json.dumps({"error": "Kode akses salah."}).encode())
                    return
                if provider not in get_all_providers(config):
                    self._set_headers(400)
                    self.wfile.write(json.dumps({
                        "error": f"Provider tidak dikenal. Pilihan: {', '.join(get_all_providers(config))}"
                    }).encode())
                    return
                config[f"{provider}_api_key"] = new_key
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                self._set_headers(200)
                self.wfile.write(json.dumps({"reply": f"✅ API key {provider} berhasil diganti dan langsung aktif!"}).encode())
                return

            # ── Chat biasa ──
            # global_ai override semua sesi kalau di-set oleh owner
            provider = global_ai or session_ai.get(session_id, "gemini")
            history = chat_sessions.setdefault(session_id, [])
            history.append({"role": "user", "text": msg})

            reply, err = call_ai(history, config, provider)
            if err:
                history.pop()
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": err}).encode())
            else:
                history.append({"role": "model", "text": reply})
                self._set_headers(200)
                self.wfile.write(json.dumps({"reply": reply}).encode())

        elif self.path == "/wa-ai":
            # Dipanggil wa.js untuk semua /ai dari WhatsApp
            # HANYA owner yang boleh — non-owner langsung ditolak
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            sender   = data.get("from", "").strip()
            provider = data.get("provider", "").strip().lower()
            owner_wa  = config.get("owner_wa", "").strip()
            owner_lid = config.get("owner_lid", "").strip()

            # Bukan owner → tolak (cek nomor WA biasa DAN format LID)
            if sender != owner_wa and sender != owner_lid:
                self._set_headers(403)
                self.wfile.write(json.dumps({
                    "reply": "❌ Hanya owner yang bisa mengganti AI."
                }).encode())
                return

            # Reset global → semua sesi bebas pilih sendiri
            if provider in ("reset", "auto", "off"):
                global_ai = None
                config["global_ai"] = None
                save_config(config)
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "reply": "🔓 Global AI dinonaktifkan — setiap sesi bebas pilih AI sendiri."
                }).encode())
                return

            all_providers = get_all_providers(config)
            if provider not in all_providers:
                self._set_headers(400)
                self.wfile.write(json.dumps({
                    "error": f"AI '{provider}' tidak dikenal. Pilihan: {', '.join(all_providers)} | reset"
                }).encode())
                return

            # Owner valid → set global AI dan simpan ke config
            global_ai = provider
            config["global_ai"] = provider
            save_config(config)
            labels = {"gemini": "Gemini 2.5 Flash", "chatgpt": "ChatGPT (GPT-4o mini)"}
            label  = labels.get(provider, provider)
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "reply": f"🌐 Global AI diganti ke *{label}* — semua sesi sekarang pakai ini!"
            }).encode())

        elif self.path == "/global-ai":
            if check_api_key(self) is None:
                self._set_headers(401)
                self.wfile.write(json.dumps({"error": "API key tidak valid. Sertakan header X-Api-Key."}).encode())
                return
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            provider = data.get("provider", "").strip().lower()
            # Reset: hapus global AI, semua sesi kembali ke pilihan masing-masing
            if provider in ("reset", "auto", "off", ""):
                global_ai = None
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "reply": "🔓 Global AI dinonaktifkan — setiap sesi sekarang bebas pilih AI sendiri."
                }).encode())
                return
            all_providers = get_all_providers(config)
            if provider not in all_providers:
                self._set_headers(400)
                self.wfile.write(json.dumps({
                    "error": f"AI '{provider}' tidak dikenal. Pilihan: {', '.join(all_providers)} | reset"
                }).encode())
                return
            global_ai = provider
            labels = {"gemini": "Gemini 2.5 Flash", "chatgpt": "ChatGPT (GPT-4o mini)"}
            label = labels.get(provider, provider)
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "reply": f"🌐 Global AI diganti ke *{label}* — semua sesi sekarang pakai ini!"
            }).encode())

        # ================= ADMIN ROUTES =================
        elif self.path.startswith("/admin/"):
            kode_req = self.headers.get("X-Access-Code", "")
            if kode_req != config.get("kode_akses"):
                self._set_headers(403)
                self.wfile.write(json.dumps({"error": "Akses Ditolak"}).encode())
                return

            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length > 0 else {}
            users = load_users()

            if self.path == "/admin/list":
                self._set_headers(200)
                self.wfile.write(json.dumps({"users": users}).encode())

            elif self.path == "/admin/create":
                new_u = data.get("new_user")
                new_p = data.get("new_pass")
                is_admin = data.get("is_admin", False)
                if new_u and new_p:
                    users[new_u] = {"password": new_p, "is_admin": is_admin}
                    save_users(users)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "created"}).encode())

            elif self.path == "/admin/delete":
                target = data.get("target_user")
                if target in users:
                    del users[target]
                    save_users(users)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "deleted"}).encode())

            elif self.path == "/admin/apikeys/list":
                out = []
                for key, meta in config.get("api_keys", {}).items():
                    out.append({
                        "key": key, "name": meta.get("name"),
                        "created": meta.get("created"),
                        "requests": meta.get("requests", 0),
                        "last_used": meta.get("last_used"),
                    })
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "keys": out, "env_master_active": bool(ENV_MASTER_KEY)
                }).encode())

            elif self.path == "/admin/apikeys/create":
                nama = (data.get("name") or "").strip()
                if not nama:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": "Nama wajib diisi."}).encode())
                    return
                new_key = secrets.token_hex(24)
                config.setdefault("api_keys", {})[new_key] = {
                    "name": nama, "created": time.time(), "requests": 0, "last_used": None
                }
                save_config(config)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "created", "key": new_key, "name": nama}).encode())

            elif self.path == "/admin/apikeys/revoke":
                target = (data.get("name") or data.get("key") or "").strip()
                keys = config.get("api_keys", {})
                to_remove = [k for k, m in keys.items() if m.get("name") == target or k == target]
                for k in to_remove:
                    del keys[k]
                save_config(config)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "revoked", "removed": len(to_remove)}).encode())

            elif self.path == "/admin/status":
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "nama_ai": config.get("nama_ai"),
                    "owner_wa": config.get("owner_wa"),
                    "global_ai": global_ai,
                    "total_users": len(users),
                    "total_api_keys": len(config.get("api_keys", {})),
                }).encode())

            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Route admin tidak ditemukan."}).encode())

def main():
    port = int(os.environ.get("PORT", config.get("port", 8000)))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print("Backend jalan di port", port)
    server.serve_forever()

if __name__ == "__main__":
    main()
