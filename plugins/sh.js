export default {
  command: ['sh', 'search'],
  handler: async (msg, sock, args) => {
    const from = msg.key.remoteJid;
    const query = args.slice(1).join(' ').trim();

    if (!query) {
      return await sock.sendMessage(from, { 
        text: `🔍 *PENCARIAN PINTAR*\n\n> *Contoh:*\n> /sh Soekarno\n> /sh Candi Borobudur` 
      }, { quoted: msg });
    }

    await sock.sendMessage(from, { text: "⏳ *Bentar dawg, lagi baca datanya...*" }, { quoted: msg });

    try {
      // 1. Cari judul artikel yang paling pas
      const searchRes = await fetch(`https://id.wikipedia.org/w/api.php?action=opensearch&search=${encodeURIComponent(query)}&limit=1&format=json`);
      const searchData = await searchRes.json();
      
      if (!searchData[1] || searchData[1].length === 0) {
        return await sock.sendMessage(from, { 
          text: `❌ Waduh king, info soal "*${query}*" kaga ketemu.` 
        }, { quoted: msg });
      }

      const exactTitle = searchData[1][0];

      // 2. Tarik langsung isi teks rangkumannya
      const detailRes = await fetch(`https://id.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(exactTitle)}`);
      const detailData = await detailRes.json();

      let replyText = `🔍 *${detailData.title}*\n\n${detailData.extract}`;

      await sock.sendMessage(from, { text: replyText }, { quoted: msg });

    } catch (error) {
      await sock.sendMessage(from, { text: `❌ Error ngab: ${error.message}` }, { quoted: msg });
    }
  }
}
