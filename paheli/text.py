"""Static Paheli777 copy. Match names and scores are filled in separately."""

from __future__ import annotations

DIVIDER = "━━━━━━━━━━━━━━━━━━"

TEXT = {
    "en": {
        "welcome": (
            "🎯 <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "🏏 Cricket  •  ⚽ Football\n"
            "🎯 Daily winner predictions\n"
            "🏆 Weekly and all-time leaderboards\n"
            "🔔 A reminder before kick-off if you have not picked\n\n"
            "Choose the winner before the match starts. "
            "An exact score adds a bonus.\n\n"
            "Choose your next move 👇"
        ),
        "settings": (
            "⚙️ <b>SETTINGS</b>\n"
            f"{DIVIDER}\n\n"
            "Choose your language. Alerts stay on the subscription you already set."
        ),
        "website": (
            "🌐 <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "The daily card lives in this chat.\n"
            "The website is one tap away when you want the full brand experience."
        ),
        "website_missing": (
            "🌐 <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "The website link is not configured yet.\n"
            "You can still play today's predictions here."
        ),
        "lang_saved": "✅ Language changed to English.",
        "sub_on": (
            "🔔 <b>MATCH ALERTS ON</b>\n\n"
            "You will get a reminder before kick-off when today's card "
            "still has a match you have not picked."
        ),
        "sub_off": (
            "🔕 <b>MATCH ALERTS OFF</b>\n\n"
            "You will no longer receive Paheli777 pick reminders."
        ),
        "help": (
            "🎯 <b>Paheli777 quick guide</b>\n\n"
            "• /start — home\n"
            "• /predict — today's winner card\n"
            "• /leaderboard — weekly and all-time\n"
            "• /mystats — points, streak, exact scores\n"
            "• /team NAME — fixtures for a club or side\n"
            "• /alerts — turn reminders on or off\n"
            "• /stop — turn reminders off\n\n"
            "Picks lock at kick-off. Correct winner is 3 points. "
            "Exact score is +2 more."
        ),
        "predict_intro": (
            "🎯 <b>TODAY'S CARD</b>\n"
            f"{DIVIDER}\n\n"
            "Pick the winner before kick-off. Exact score is optional.\n"
            "Correct winner <b>3</b> • exact score <b>+2</b>."
        ),
        "no_matches": (
            "No notable matches are on the card yet.\n"
            "Check upcoming fixtures, or open this again closer to the day's games."
        ),
        "locked": "🔒 This pick is locked. Kick-off has passed.",
        "interested": (
            "🙋 <b>You are on the list.</b>\n\n"
            "We have noted your interest in Paheli777.\n"
            "Today's card is ready whenever you are."
        ),
    },
    "hi": {
        "welcome": (
            "🎯 <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "🏏 क्रिकेट  •  ⚽ फुटबॉल\n"
            "🎯 रोज़ का विनर प्रेडिक्शन\n"
            "🏆 वीकली और ऑल-टाइम लीडरबोर्ड\n"
            "🔔 किकऑफ से पहले रिमाइंडर, अगर पिक बाकी हो\n\n"
            "मैच शुरू होने से पहले विनर चुनें. सही स्कोर पर बोनस अंक.\n\n"
            "नीचे से चुनें 👇"
        ),
        "settings": (
            "⚙️ <b>SETTINGS</b>\n"
            f"{DIVIDER}\n\n"
            "भाषा चुनें. अलर्ट आपकी मौजूदा सब्सक्रिप्शन पर ही रहेंगे."
        ),
        "website": (
            "🌐 <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "रोज़ का कार्ड इसी चैट में है.\n"
            "पूरी ब्रांड साइट एक टैप पर खुलती है."
        ),
        "website_missing": (
            "🌐 <b>PAHELI777</b>\n"
            f"{DIVIDER}\n\n"
            "वेबसाइट लिंक अभी सेट नहीं है.\n"
            "आज के प्रेडिक्शन यहीं खेल सकते हैं."
        ),
        "lang_saved": "✅ भाषा हिंदी कर दी गई है.",
        "sub_on": (
            "🔔 <b>MATCH ALERTS ON</b>\n\n"
            "आज के कार्ड पर जिस मैच का पिक नहीं है, उसके किकऑफ से पहले रिमाइंडर मिलेगा."
        ),
        "sub_off": (
            "🔕 <b>MATCH ALERTS OFF</b>\n\n"
            "अब Paheli777 पिक रिमाइंडर नहीं मिलेंगे."
        ),
        "help": (
            "🎯 <b>Paheli777 गाइड</b>\n\n"
            "• /start — होम\n"
            "• /predict — आज का कार्ड\n"
            "• /leaderboard — लीडरबोर्ड\n"
            "• /mystats — अंक और स्ट्रीक\n"
            "• /team NAME — टीम के मैच\n"
            "• /alerts — रिमाइंडर ऑन या ऑफ\n"
            "• /stop — रिमाइंडर बंद\n\n"
            "पिक किकऑफ पर लॉक होते हैं. सही विनर 3 अंक, सही स्कोर +2."
        ),
        "predict_intro": (
            "🎯 <b>आज का कार्ड</b>\n"
            f"{DIVIDER}\n\n"
            "किकऑफ से पहले विनर चुनें. सही स्कोर ऑप्शनल है.\n"
            "सही विनर <b>3</b> • सही स्कोर <b>+2</b>."
        ),
        "no_matches": (
            "आज के कार्ड पर अभी कोई खास मैच नहीं है.\n"
            "अपकमिंग फिक्स्चर देखें, या थोड़ी देर बाद फिर खोलें."
        ),
        "locked": "🔒 यह पिक लॉक हो चुका है. किकऑफ हो गया है.",
        "interested": (
            "🙋 <b>आप लिस्ट में हैं.</b>\n\n"
            "Paheli777 में आपकी दिलचस्पी नोट कर ली है.\n"
            "आज का कार्ड तैयार है."
        ),
    },
}


def t(lang: str, key: str) -> str:
    bundle = TEXT.get(lang) or TEXT["en"]
    if key in bundle:
        return bundle[key]
    return TEXT["en"][key]
