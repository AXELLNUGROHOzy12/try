export default {
  command: ['ssweb', 'ss', 'webss'], // Alias command sesuai request lu
  handler: async (msg, sock, args) => {
    const from = msg.key.remoteJid;
    // Gabungin argumen jadi satu teks (karena args[0] itu nama command-nya)
    let text = args.slice(1).join(' ').trim();

    if (!text) {
      return await sock.sendMessage(from, { 
        text: `📸 *SCREENSHOT WEB*\n\n> Screenshot halaman website\n\n> *Contoh:*\n> /ssweb https://google.com\n> /ss https://github.com --mobile` 
      }, { quoted: msg });
    }

    // Deteksi mode mobile/hp
    let mode = "desktop";
    if (text.includes("--mobile") || text.includes("--hp")) {
      mode = "mobile";
      text = text.replace(/--mobile|--hp/g, "").trim();
    }

    // Tambahin https:// kalo user lupa
    if (!text.startsWith("http")) {
      text = "https://" + text;
    }

    await sock.sendMessage(from, { text: "⏳ *Tunggu bentar dawg, lagi ngefoto webnya...*" }, { quoted: msg });

    try {
      // Logic ambil screenshot (pake fetch bawaan, ga perlu axios)
      const width = mode === "mobile" ? 720 : 1920;
      const apiUrl = `https://image.thum.io/get/width/${width}/crop/1080/noanimate/${text}`;
      
      const res = await fetch(apiUrl);
      if (!res.ok) throw new Error('Gagal narik gambar dari server thum.io');
      
      const imageBuffer = Buffer.from(await res.arrayBuffer());

      // Kirim hasil gambar
      await sock.sendMessage(from, { 
        image: imageBuffer, 
        caption: `📸 Hasil screenshot:\n${text}` 
      }, { quoted: msg });

    } catch (error) {
      await sock.sendMessage(from, { text: `❌ Error: ${error.message}` }, { quoted: msg });
    }
  }
}
