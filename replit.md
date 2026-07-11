# DeepSeek R1 Chat Backend

A lightweight Python HTTP server that proxies chat messages to the free DeepSeek R1 API at `api.siputzx.my.id`. No API key required.

## How to run

The workflow **"Start application"** runs `python back.py` and serves on **port 8000**.

On first run it auto-creates `config.json` with default settings.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/status` | Health check + current AI/user name |
| POST | `/chat` | Send a message (`session_id`, `message`) |
| POST | `/reset` | Clear chat history for a session |
| POST | `/verifikasi-kode` | Verify access code |
| POST | `/personalisasi` | Update AI name/personality (requires `X-Access-Code` header) |

## Configuration (`config.json`)

| Key | Default | Description |
|-----|---------|-------------|
| `nama_ai` | `Nova` | AI name |
| `nama_user` | `Kamu` | User name shown in prompts |
| `kepribadian` | friendly assistant | Personality/system prompt |
| `kode_akses` | `SXIELD1` | Access code for personalization endpoint |
| `port` | `8000` | Port the server listens on |

Edit `config.json` and restart the workflow to apply changes.

## User preferences
