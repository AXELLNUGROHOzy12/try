FROM node:20-bookworm-slim

# Python (back.py cuma pakai stdlib, jadi tidak perlu pip install apapun)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependency Node dulu (layer cache lebih efisien)
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

# Copy sisa source code
COPY . .

RUN chmod +x start.sh

# Railway inject $PORT otomatis saat runtime, jangan di-hardcode di sini
EXPOSE 8000

CMD ["./start.sh"]
