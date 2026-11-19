"""Edit this file to change what /start sends."""

# Message 1: image. Local path, https URL, or a Telegram file_id.
WELCOME_IMAGE = "assets/welcome.jpg"

# Message 2: plain text
WELCOME_TEXT_1 = (
    "👋 <b>Welcome!</b>\n\n"
    "Thanks for starting the bot. Here's what you'll get here."
)

# Message 3: text + button links
WELCOME_TEXT_2 = "👇 <b>Join us on our channels:</b>"
WELCOME_BUTTONS = [
    ("📢 Join Channel", "https://t.me/yourchannel"),
    ("💬 Join Group", "https://t.me/yourgroup"),
    ("🌐 Website", "https://example.com"),
]
