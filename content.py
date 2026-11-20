"""Edit this file to change texts, buttons, images and languages."""

# ───────── /start sequence ─────────
# Message 1: image. Local path, https URL, or a Telegram file_id.
WELCOME_IMAGE = "https://graph.org/file/cbf5547703f8a36a24075-5dc592e610805e0b6a.jpg"

# Message 2: plain text
WELCOME_TEXT_1 = (
    "👋 <b>Welcome!</b>\n\n"
    "Thanks for starting the bot. Here's what you'll get here."
)

# Message 3: text + buttons
WELCOME_TEXT_2 = "👇 <b>Join us on our channels:</b>"
WELCOME_BUTTONS = [
    ("📢 Join Us", "https://t.me/+ngKKWcsK5agwNDQ1"),
]

# Extra buttons on the /start message: Preview (top) and Support (bottom)
PREVIEW_BTN = "👀 Preview"
SUPPORT_BTN = "💬 24x7 Support"

# ───────── Preview flow ─────────
CHOOSE_LANG_TEXT = "🌐 <b>Choose your language</b>\n<b>अपनी भाषा चुनें</b>"

# 3-4 images sent as an album after a language is picked.
# Local paths or https URLs. Missing files are skipped.
PREVIEW_IMAGES = [
    "assets/preview1.jpg",
    "assets/preview2.jpg",
    "assets/preview3.jpg",
]

# Where the button under the preview leads
PREVIEW_LINK = "https://t.me/+QdxxHDiLQ95jNzY1"

# Add/remove languages freely. Key = any short code.
LANGUAGES = {
    "en": {
        "name": "🇬🇧 English",
        "text": "✅ Here's a quick preview. Tap below to get full access:",
        "button": "🚀 Get Full Access",
    },
    "hi": {
        "name": "🇮🇳 हिन्दी",
        "text": "✅ यह रहा एक छोटा सा प्रीव्यू। पूरा एक्सेस पाने के लिए नीचे टैप करें:",
        "button": "🚀 पूरा एक्सेस पाएं",
    },
    "bn": {
        "name": "🇧🇩 বাংলা",
        "text": "✅ এই নিন একটি ছোট প্রিভিউ। সম্পূর্ণ অ্যাক্সেস পেতে নিচে ট্যাপ করুন:",
        "button": "🚀 সম্পূর্ণ অ্যাক্সেস নিন",
    },
    "es": {
        "name": "🇪🇸 Español",
        "text": "✅ Aquí tienes una vista previa rápida. Toca abajo para acceder a todo:",
        "button": "🚀 Obtener acceso completo",
    },
    "pt": {
        "name": "🇧🇷 Português",
        "text": "✅ Aqui está uma prévia rápida. Toque abaixo para acessar tudo:",
        "button": "🚀 Obter acesso completo",
    },
}

# ───────── Support ─────────
SUPPORT_TEXT = (
    "💬 <b>24x7 Support</b>\n\n"
    "Send your message here: text, links, photos, videos, files or voice notes "
    "all work. Our team will reply to you in this chat.\n\n"
    "Send /cancel to leave support mode."
)
