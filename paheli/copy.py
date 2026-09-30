"""Paheli777 copy. English and Hindi for the screens people see first."""

from __future__ import annotations

from paheli.matches import DIVIDER


TEXT = {
    "en": {
        "welcome": (
            "⚡ <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "🏟 <b>Daily predictions. Live scores. One place.</b>\n\n"
            "🏏 Cricket scores, fixtures and news\n"
            "⚽ Football scores, fixtures and news\n"
            "🎯 Predict today's winners\n"
            "🏆 Weekly and all-time leaderboards\n\n"
            "Picks lock at kick-off. Points are for the leaderboard.\n\n"
            "Choose your next move 👇"
        ),
        "settings": (
            "⚙️ <b>SETTINGS</b>\n"
            f"{DIVIDER}\n\n"
            "Choose your language. Match alerts and prediction reminders stay as they are."
        ),
        "alerts_on": (
            "🔔 <b>MATCH ALERTS ON</b>\n\n"
            "You will get a reminder before kick-off when you still have not picked, "
            "plus occasional Paheli777 updates."
        ),
        "alerts_off": (
            "🔕 <b>MATCH ALERTS OFF</b>\n\n"
            "Broadcasts are off. If you have predicted before, you can still get a "
            "one-time reminder for a match you have not picked."
        ),
        "lang_saved": "✅ Language changed to English.",
        "website": (
            "🌐 <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "Open the Paheli777 website for the latest from the brand.\n\n"
            "The prediction game on this bot is free to play. Points do not cash out."
        ),
        "website_missing": (
            "🌐 <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "The website link is not configured yet. Set BRAND_URL and restart the bot."
        ),
    },
    "hi": {
        "welcome": (
            "⚡ <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "🏟 <b>रोज़ की prediction. लाइव स्कोर. एक ही जगह.</b>\n\n"
            "🏏 क्रिकेट स्कोर, फिक्स्चर और न्यूज़\n"
            "⚽ फुटबॉल स्कोर, फिक्स्चर और न्यूज़\n"
            "🎯 आज के मैच का विजेता चुनें\n"
            "🏆 वीकली और ऑल-टाइम लीडरबोर्ड\n\n"
            "पिक किक-ऑफ पर लॉक हो जाती है. पॉइंट्स सिर्फ लीडरबोर्ड के लिए हैं.\n\n"
            "अपना विकल्प चुनें 👇"
        ),
        "settings": (
            "⚙️ <b>SETTINGS</b>\n"
            f"{DIVIDER}\n\n"
            "भाषा चुनें. मैच अलर्ट और prediction reminder जैसे हैं वैसे रहेंगे."
        ),
        "alerts_on": (
            "🔔 <b>MATCH ALERTS ON</b>\n\n"
            "जिस मैच की पिक आपने नहीं की, उसकी किक-ऑफ से पहले reminder मिलेगा."
        ),
        "alerts_off": (
            "🔕 <b>MATCH ALERTS OFF</b>\n\n"
            "Broadcast बंद हैं. अगर आप पहले prediction कर चुके हैं, "
            "तो बिना पिक वाले मैच का एक reminder अब भी आ सकता है."
        ),
        "lang_saved": "✅ भाषा हिंदी कर दी गई है.",
        "website": (
            "🌐 <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "Paheli777 की वेबसाइट खोलें.\n\n"
            "इस बॉट की prediction game फ्री है. पॉइंट्स कैश नहीं होते."
        ),
        "website_missing": (
            "🌐 <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "वेबसाइट लिंक अभी सेट नहीं है. BRAND_URL जोड़कर बॉट दोबारा चलाएँ."
        ),
    },
}


def t(lang: str, key: str) -> str:
    bucket = TEXT.get(lang) or TEXT["en"]
    return bucket.get(key) or TEXT["en"][key]


def help_text() -> str:
    return (
        "⚡ <b>Paheli777 guide</b>\n"
        f"{DIVIDER}\n\n"
        "• /start — home menu\n"
        "• /predict — today's prediction board\n"
        "• /leaderboard — weekly ranks\n"
        "• /mystats — your points and streak\n"
        "• /team NAME — find a cricket or football team\n"
        "• /sports — coverage check\n\n"
        "Correct winner = 3 points. Exact score = 2 bonus points. "
        "Picks lock at kick-off."
    )


def footer() -> str:
    return f"\n\n{DIVIDER}\n🎯 <b>Paheli777</b> • Predict it. Follow it."
