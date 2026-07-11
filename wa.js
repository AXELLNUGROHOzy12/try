import makeWASocket, { DisconnectReason, useMultiFileAuthState, fetchLatestBaileysVersion } from '@whiskeysockets/baileys'
import { Boom } from '@hapi/boom'
import fs from 'fs'
import { writeFile } from 'fs/promises'
import path from 'path'
import { fileURLToPath, pathToFileURL } from 'url'
import QRCode from 'qrcode'
import { Sticker, StickerTypes } from 'wa-sticker-formatter'
import SoundCloud from 'soundcloud-scraper'

const scClient = new SoundCloud.Client()

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const PORT = process.env.PORT || 8000
const BACKEND = process.env.BACKEND_URL || `http://localhost:${PORT}`

// Baca nama config buat display doang
const configPath = path.join(__dirname, 'config.json')
let configData = {}
let OWNER_NAME = 'exel'
try {
  configData = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
  if (configData.nama_user) OWNER_NAME = configData.nama_user
} catch (e) {}

const QR_FILE = 'qr_current.txt'
const QR_IMAGE = 'qr_current.png'
const SELF_FILE = 'self_mode.txt'
const SEEN_FILE = 'seen_users.json'
const DS_FILE = 'ds_mode.txt'

// ── Tunggu Backend Siap ──
async function waitForBackend(maxRetries = 15, delayMs = 1000) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const r = await fetch(`${BACKEND}/status`)
      if (r.ok) return true
    } catch {}
    await new Promise(res => setTimeout(res, delayMs))
  }
  return false
}
await waitForBackend()

let selfMode = false
try { selfMode = fs.readFileSync(SELF_FILE, 'utf-8').trim() === '1' } catch {}

let dsMode = false
try { dsMode = fs.readFileSync(DS_FILE, 'utf-8').trim() === '1' } catch {}

let seenUsers = new Set()
try { seenUsers = new Set(JSON.parse(fs.readFileSync(SEEN_FILE, 'utf-8'))) } catch {}

async function setSelfMode(val) {
  selfMode = val
  await writeFile(SELF_FILE, val ? '1' : '0', 'utf-8')
}

async function setDsMode(val) {
  dsMode = val
  await writeFile(DS_FILE, val ? '1' : '0', 'utf-8')
}

async function markSeen(jid) {
  seenUsers.add(jid)
  await writeFile(SEEN_FILE, JSON.stringify([...seenUsers]), 'utf-8')
}

function buildWelcome(aiName) {
  return (
    `Halo! 👋 Selamat datang!\n\n` +
    `Perkenalkan, aku *${aiName}* — asisten AI yang siap membantu kamu.\n\n` +
    `Bot ini dibuat oleh *${OWNER_NAME}*.\n\n` +
    `Silakan mulai chat! 😊`+
    `Note:Owner hanya mengizinkan aktivitas yang legal tanpa ada nya eksploitasi!`
  )
}

// ── Sistem Auto-Load Plugin ──
const plugins = {}
const pluginDir = path.join(__dirname, 'plugins')
if (!fs.existsSync(pluginDir)) fs.mkdirSync(pluginDir)

const loadPlugins = async () => {
  const files = fs.readdirSync(pluginDir).filter(f => f.endsWith('.js'))
  for (const file of files) {
    const pluginUrl = pathToFileURL(path.join(pluginDir, file)).href
    const plugin = await import(pluginUrl)
    if (plugin.default && plugin.default.command) {
      plugin.default.command.forEach(cmd => {
        plugins[cmd] = plugin.default.handler
      })
    }
  }
}
await loadPlugins()

// ── Main Bot Connection ──
async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState('wa_auth')
  const { version } = await fetchLatestBaileysVersion()

  const sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: true,
    browser: ['Nova AI', 'Chrome', '125.0.0']
  })

  sock.ev.on('connection.update', async update => {
    const { connection, lastDisconnect, qr } = update
    if (qr) {
      await writeFile(QR_FILE, qr, 'utf-8')
      await QRCode.toFile(QR_IMAGE, qr, { width: 300, margin: 2 })
    }
    if (connection === 'close') {
      const code = new Boom(lastDisconnect?.error)?.output?.statusCode
      const shouldReconnect = code !== DisconnectReason.loggedOut
      if (shouldReconnect) connectToWhatsApp()
      else await writeFile(QR_FILE, 'loggedout', 'utf-8')
    }
    if (connection === 'open') {
      await writeFile(QR_FILE, 'connected', 'utf-8')
    }
  })

  sock.ev.on('creds.update', saveCreds)

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return
    const msg = messages[0]
    if (!msg?.message) return 

    const from = msg.key.remoteJid
    const isGroup = from.endsWith('@g.us')
    
    // Ambil JID murni (bisa deteksi grup/personal/LID)
    const senderRaw = msg.key.participant || msg.key.remoteJid || ''
    
    // PROTEKSI HARDCODE UTAMA
    const isOwner = msg.key.fromMe || 
                    senderRaw.includes('628772703519') || 
                    senderRaw.includes('264643620647015')

    if (msg.key.fromMe && !isOwner) return 

    const text = msg.message.conversation || msg.message.extendedTextMessage?.text || msg.message.imageMessage?.caption || ''
    if (!text.trim()) return

    const args = text.trim().split(/ +/)
    const command = args[0].toLowerCase().replace(/^[\/\.#]/, '')
    const cmdFull = text.trim().toLowerCase()

    // ── FITUR /DS (DISCONNECT) ──
    if (command === 'ds') {
      if (!isOwner) {
        // 🔥 DEBUG MODE: Langsung nampilin string ID lu biar ketahuan salahnya di mana
        return await sock.sendMessage(from, { 
          text: `❌ *AKSES DITOLAK*\n\nID lu kaga cocok mase.\n> *ID Detector:* \`${senderRaw}\`\n\nPastikan ID di atas ada di list hardcode wa.js!` 
        }, { quoted: msg })
      }

      await setDsMode(!dsMode)
      await sock.sendMessage(from, { text: dsMode ? '🛑 *DISCONNECT MODE ON*\nSemua fitur dimatikan sementara (kecuali /ping).' : '✅ *DISCONNECT MODE OFF*\nSemua fitur kembali aktif mase!' }, { quoted: msg })
      return
    }

    // Blokir semua aktivitas kalo DS Mode nyala (kecuali /ping)
    if (dsMode && command !== 'ping') {
      return 
    }

    // 1. Eksekusi Plugin Dulu
    if (plugins[command]) {
      try {
        await plugins[command](msg, sock, args)
        return
      } catch (e) {
        await sock.sendMessage(from, { text: '❌ Error plugin: ' + e.message })
      }
    }

    // ── FITUR BAWAAN WA.JS ──
    if (cmdFull.startsWith('/sc ')) {
      const query = text.trim().substring(4).trim()
      try {
        await sock.sendMessage(from, { text: '🔍 Mencari di SoundCloud...' })
        const searchResult = await scClient.search(query, 'track')
        if (!searchResult.length) return await sock.sendMessage(from, { text: '❌ Lagu ga ketemu.' })
        
        const track = searchResult[0]
        const apiRes = await fetch(`https://api.siputzx.my.id/api/d/soundcloud?url=${encodeURIComponent(track.url)}`)
        const apiData = await apiRes.json()
        const audioUrl = apiData?.data?.url
        if (!audioUrl) throw new Error('Gagal dapet link.')
        const audioBuffer = Buffer.from(await (await fetch(audioUrl)).arrayBuffer())
        await sock.sendMessage(from, { audio: audioBuffer, mimetype: 'audio/mp4' }, { quoted: msg })
      } catch (e) {
        await sock.sendMessage(from, { text: '❌ Error: ' + e.message })
      }
      return
    }

    if (cmdFull.startsWith('/spotify ')) {
      const url = text.trim().split(' ')[1]
      try {
        await sock.sendMessage(from, { text: '⏳ Menarik lagu dari Spotify...' })
        const apiRes = await fetch(`https://api.siputzx.my.id/api/d/spotify?url=${encodeURIComponent(url)}`)
        const apiData = await apiRes.json()
        const audioUrl = apiData?.data?.download || apiData?.url 
        if (!audioUrl) throw new Error('Gagal dapet link.')
        const audioBuffer = Buffer.from(await (await fetch(audioUrl)).arrayBuffer())
        await sock.sendMessage(from, { audio: audioBuffer, mimetype: 'audio/mp4' }, { quoted: msg })
      } catch (e) {
        await sock.sendMessage(from, { text: '❌ Error: ' + e.message })
      }
      return
    }

    if (cmdFull.startsWith('/brat ')) {
      const bratText = text.trim().substring(6).trim()
      try {
        const apiRes = await fetch(`https://api.siputzx.my.id/api/m/brat?text=${encodeURIComponent(bratText)}`)
        const buffer = Buffer.from(await apiRes.arrayBuffer())
        const stickerMeta = new Sticker(buffer, { pack: 'Brat', author: OWNER_NAME, type: StickerTypes.FULL })
        await sock.sendMessage(from, { sticker: await stickerMeta.toBuffer() })
      } catch (e) {
        await sock.sendMessage(from, { text: '❌ Gagal bikin stiker.' })
      }
      return
    }

    if (cmdFull.startsWith('/dd ')) {
      const tiktokUrl = text.trim().split(' ')[1]
      try {
        const apiRes = await fetch(`https://www.tikwm.com/api/?url=${tiktokUrl}`)
        const apiData = await apiRes.json()
        const videoUrl = apiData?.data?.hdplay || apiData?.data?.play
        if (!videoUrl) throw new Error('Ga dapet video.')
        const buffer = Buffer.from(await (await fetch(videoUrl)).arrayBuffer())
        await sock.sendMessage(from, { video: buffer, mimetype: 'video/mp4' })
      } catch (e) {
        await sock.sendMessage(from, { text: '❌ Error: ' + e.message })
      }
      return
    }

    // ── FITUR LAMA (BACKEND AI & FALLBACK) ──
    if (cmdFull.startsWith('/ai ')) {
      const provider = text.trim().split(' ').slice(1).join(' ').trim().toLowerCase()
      const fromNumber = from.split('@')[0].split(':')[0]
      try {
        const res  = await fetch(`${BACKEND}/wa-ai`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ from: fromNumber, session_id: from, provider })
        })
        const data = await res.json()
        await sock.sendMessage(from, { text: data.reply || data.error })
      } catch (e) {
        await sock.sendMessage(from, { text: '❌ Error AI: Backend lu mati atau belum konek.' })
      }
      return
    }

    if (cmdFull === '/self') {
      if (!isOwner) {
        return await sock.sendMessage(from, { 
          text: `❌ *AKSES DITOLAK*\n\n> *ID Detector:* \`${senderRaw}\`` 
        }, { quoted: msg })
      }
      await setSelfMode(!selfMode)
      await sock.sendMessage(from, { text: selfMode ? '✅ Self mode ON' : '🔓 Self mode OFF' })
      return
    }

    if (selfMode && isGroup) return

    if (!seenUsers.has(from)) {
      await markSeen(from)
      try {
        await sock.sendMessage(from, { text: buildWelcome(configData.nama_ai || 'Nova AI') })
      } catch {
        await sock.sendMessage(from, { text: buildWelcome('Nova AI') })
      }
    }

    try {
      const res = await fetch(`${BACKEND}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: from, message: text })
      })
      const data = await res.json()
      if (data.reply || data.error) {
        await sock.sendMessage(from, { text: data.reply || data.error })
      }
    } catch (e) {}
  })
}

connectToWhatsApp().catch(console.error)
