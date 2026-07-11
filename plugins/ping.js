import { performance } from 'perf_hooks'
import os from 'os'

const formatUptime = (seconds) => {
  const d = Math.floor(seconds / (3600 * 24))
  const h = Math.floor((seconds % (3600 * 24)) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return `${d}h ${h}m ${m}s ${s}s`
}

export default {
  command: ['ping', 'speed', 'p'],
  handler: async (msg, sock) => {
    const start = performance.now()
    const from = msg.key.remoteJid

    const sentMsg = await sock.sendMessage(from, { text: "⏳ *Pinging...*" }, { quoted: msg })

    const end = performance.now()
    const latency = (end - start).toFixed(2)
    const usedMem = ((os.totalmem() - os.freemem()) / 1024 / 1024).toFixed(0)
    const uptime = formatUptime(process.uptime())

    await sock.sendMessage(from, {
      text:
`╭━━━━◈ 🏓 𝗣𝗢𝗡𝗚! ◈━━━━╮
┃  ⌬ Latency › *${latency} ms*
┃  ⌬ Status  › *Online ✅*
┃  ⌬ Uptime  › *${uptime}*
┃  ⌬ RAM     › *${usedMem} MB*
╰━━━━━━━━━━━━━━━━━━━━━⬣`,
      edit: sentMsg.key,
    })
  }
}
