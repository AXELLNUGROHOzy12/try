#!/bin/bash
set -e

echo "🚀 Starting Nova AI backend (Python) on port ${PORT:-8000}..."
python3 back.py &
BACK_PID=$!

# Kalau back.py mati, seluruh container ikut mati (biar Railway restart otomatis)
trap "echo '🛑 Shutting down...'; kill -TERM $BACK_PID 2>/dev/null; exit 0" SIGTERM SIGINT

echo "🚀 Starting WhatsApp bot (Node.js)..."
(
  # wa.js boleh crash-loop tanpa menjatuhkan backend utama
  while true; do
    node wa.js
    echo "⚠️  wa.js berhenti, restart dalam 5 detik..."
    sleep 5
  done
) &
WA_PID=$!

# Kalau proses backend Python mati (fatal), seluruh container ikut berhenti
wait $BACK_PID
echo "❌ back.py berhenti, menghentikan container."
kill $WA_PID 2>/dev/null || true
exit 1
