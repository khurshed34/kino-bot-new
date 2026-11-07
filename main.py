
import os
import json
import base64
import asyncio
import urllib.request
import urllib.error

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6777943949

MAIN_CHANNEL = "@kinoj90"
STORAGE_CHANNEL = "@ripm6"
DB_FILE = "movies.json"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPOSITORY = os.getenv("GITHUB_REPOSITORY", "khurshed34/kino-bot-new")
BRANCH = os.getenv("GITHUB_REF_NAME", "main")

REQUIRED_CHANNELS = [
    {"id": "@merlin267", "url": "https://t.me/merlin267"},
    {"id": -1004473443170, "url": "https://t.me/+gWWLvmg8BMsyZmUy"},
    {"id": "@kinoj90", "url": "https://t.me/kinoj90"}
]

def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("movies", {})
                data.setdefault("users", [])
                data.setdefault("requests", 0)
                return data
    except Exception:
        pass

    return {"movies": {}, "users": [], "requests": 0}


db = load_db()


def save_local():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def github_backup():
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN missing")
        return

    url = (
        f"https://api.github.com/repos/{REPOSITORY}"
        f"/contents/{DB_FILE}?ref={BRANCH}"
    )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    sha = None

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            sha = json.loads(response.read()).get("sha")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            print("GitHub read error:", error)
            return

    content = json.dumps(db, ensure_ascii=False, indent=2)

    payload = {
        "message": "Save movie database",
        "content": base64.b64encode(
            content.encode("utf-8")
        ).decode("utf-8"),
        "branch": BRANCH
    }

    if sha:
        payload["sha"] = sha

    req = urllib.request.Request(
        url.split("?")[0],
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="PUT"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            print("GitHub backup OK:", response.status)
    except Exception as error:
        print("GitHub backup failed:", error)


async def save_database():
    save_local()
    await asyncio.to_thread(github_backup)


def is_admin(user_id):
    return user_id == ADMIN_ID


def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Иловаи кино", callback_data="add")],
        [InlineKeyboardButton("🗑 Нест кардани кино", callback_data="delete")],
        [InlineKeyboardButton("📊 Омори бот", callback_data="stats")]
    ])


async def check_subscription(user_id, context):
    missing = []

    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(
                channel["id"], user_id
            )

            if member.status in ("member", "administrator", "creator"):
                continue

            if member.status == "restricted" and member.is_member:
                continue

            missing.append(channel)

        except Exception as error:
            print("Subscription error:", error)
            missing.append(channel)

    return missing


def sub_keyboard(missing):
    buttons = []

    for channel in missing:
        buttons.append([
            InlineKeyboardButton(
                "➕ Обуна шудан",
                url=channel["url"]
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "✅ Санҷиши обуна",
            callback_data="check"
        )
    ])

    return InlineKeyboardMarkup(buttons)


async def send_movie(chat_id, context, code):
    movie = db["movies"].get(str(code))

    if not movie:
        await context.bot.send_message(
            chat_id,
            "❌ Ин кино дар база нест!"
        )
        return

    await context.bot.send_video(
        chat_id=chat_id,
        video=movie["file_id"],
        caption=movie.get("title", "🎬 Кино")
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id not in db["users"]:
        db["users"].append(user_id)
        await save_database()

    if is_admin(user_id) and not context.args:
        await update.message.reply_text(
            "👑 Панели админ",
            reply_markup=admin_keyboard()
        )
        return

    if not context.args:
        await update.message.reply_text(
            "🎬 Хуш омадед!\n"
            "Барои гирифтани кино тугмаи Тамошоро аз канали мо пахш кунед."
        )
        return

    code = context.args[0]
    context.user_data["movie_code"] = code

    missing = await check_subscription(user_id, context)

    if missing:
        await update.message.reply_text(
            "❗ Барои гирифтани кино ба ҳамаи каналҳо обуна шавед:",
            reply_markup=sub_keyboard(missing)
        )
        return

    await send_movie(update.effective_chat.id, context, code)


async def check_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    code = context.user_data.get("movie_code")

    if not code:
        await query.message.reply_text("Рамзи кино ёфт нашуд.")
        return

    missing = await check_subscription(query.from_user.id, context)

    if missing:
        await query.message.reply_text(
            "❗ Ҳоло ба ҳамаи каналҳо обуна нестед:",
            reply_markup=sub_keyboard(missing)
        )
        return

    await send_movie(query.message.chat_id, context, code)


async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    if query.data == "add":
        context.user_data["state"] = "full_video"
        await query.message.reply_text(
            "📹 Видеои пурраи киноро ба ман фиристед."
        )

    elif query.data == "delete":
        context.user_data["state"] = "delete"
        await query.message.reply_text(
            "Рамзи киноеро, ки нест кардан мехоҳед, фиристед."
        )

    elif query.data == "stats":
        await query.message.reply_text(
            "📊 ОМОРИ БОТ\n\n"
            f"👥 Истифодабарандагон: {len(db['users'])}\n"
            f"🎬 Киноҳо: {len(db['movies'])}\n"
            f"🔎 Дархостҳо: {db['requests']}"
        )


async def admin_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    state = context.user_data.get("state")

    if state == "full_video":
        try:
            forwarded = await context.bot.forward_message(
                chat_id=STORAGE_CHANNEL,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id
            )

            video = forwarded.video

            if not video:
                await update.message.reply_text(
                    "❌ Видеоро ҳамчун видео фиристед."
                )
                return

            context.user_data["pending_file_id"] = video.file_id
            context.user_data["state"] = "title"

            await update.message.reply_text(
                "✅ Видео дар канали хусусӣ нигоҳ дошта шуд.\n"
                "Акнун номи киноро нависед."
            )

        except Exception as error:
            print("Storage error:", error)
            await update.message.reply_text(
                "❌ Видео ба канали хусусӣ фиристода нашуд. "
                "Иҷозати администраторро санҷед."
            )

    elif state == "preview":
        context.user_data["preview"] = {
            "type": "video",
            "file_id": update.message.video.file_id
        }
        await publish_movie(update, context)


async def admin_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if context.user_data.get("state") != "preview":
        return

    context.user_data["preview"] = {
        "type": "photo",
        "file_id": update.message.photo[-1].file_id
    }

    await publish_movie(update, context)


async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    state = context.user_data.get("state")
    value = update.message.text.strip()

    if state == "title":
        context.user_data["title"] = value
        context.user_data["state"] = "description"

        await update.message.reply_text(
            "📝 Маълумоти кӯтоҳ дар бораи кино нависед."
        )

    elif state == "description":
        context.user_data["description"] = value
        context.user_data["state"] = "preview"

        await update.message.reply_text(
            "🖼 Акнун сурат ё трейлери кӯтоҳ фиристед.\n"
            "Агар пешнамоиш лозим набошад, /publish нависед."
        )

    elif state == "delete":
        code = value

        if code in db["movies"]:
            del db["movies"][code]
            await save_database()
            await update.message.reply_text(
                f"✅ Кинои {code} нест карда шуд."
            )
        else:
            await update.message.reply_text(
                "❌ Ин рамз ёфт нашуд."
            )

        context.user_data.clear()


async def publish_movie(update, context):
    user_data = context.user_data

    file_id = user_data.get("pending_file_id")
    title = user_data.get("title")
    description = user_data.get("description")

    if not file_id or not title or not description:
        await update.effective_message.reply_text(
            "❌ Маълумот пурра нест."
        )
        return

    numbers = [int(x) for x in db["movies"] if str(x).isdigit()]
    code = str(max(numbers, default=100) + 1)

    bot_info = await context.bot.get_me()
    watch_url = f"https://t.me/{bot_info.username}?start={code}"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎬 Тамошо", url=watch_url)
    ]])

    caption = (
        f"🎬 {title}\n\n"
        f"{description}\n\n"
        f"🔢 Рамзи кино: {code}"
    )

    preview = user_data.get("preview")

    try:
        if preview and preview["type"] == "photo":
            await context.bot.send_photo(
                MAIN_CHANNEL,
                photo=preview["file_id"],
                caption=caption,
                reply_markup=keyboard
            )

        elif preview and preview["type"] == "video":
            await context.bot.send_video(
                MAIN_CHANNEL,
                video=preview["file_id"],
                caption=caption,
                reply_markup=keyboard
            )

        else:
            await context.bot.send_message(
                MAIN_CHANNEL,
                text=caption,
                reply_markup=keyboard
            )

        db["movies"][code] = {
            "file_id": file_id,
            "title": title,
            "description": description
        }

        await save_database()

        await update.effective_message.reply_text(
            f"✅ Кино нашр шуд!\n"
            f"🎬 {title}\n"
            f"🔢 Рамз: {code}",
            reply_markup=admin_keyboard()
        )

    except Exception as error:
        print("Publish error:", error)
        await update.effective_message.reply_text(
            "❌ Нашри кино иҷро нашуд. "
            "Иҷозати администраторро санҷед."
        )

    context.user_data.clear()


async def publish_command(update, context):
    if not is_admin(update.effective_user.id):
        return

    if context.user_data.get("state") != "preview":
        return

    await publish_movie(update, context)


async def admin_command(update, context):
    if not is_admin(update.effective_user.id):
        return

    context.user_data.clear()

    await update.message.reply_text(
        "👑 Панели админ",
        reply_markup=admin_keyboard()
    )


async def post_init(app):
    print("KINO BOT STARTED")
    print("Movies loaded:", len(db["movies"]))


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN ёфт нашуд!")

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("publish", publish_command))

    app.add_handler(CallbackQueryHandler(
        check_button, pattern="^check$"
    ))

    app.add_handler(CallbackQueryHandler(
        admin_buttons, pattern="^(add|delete|stats)$"
    ))

    app.add_handler(MessageHandler(
        filters.VIDEO, admin_video
    ))

    app.add_handler(MessageHandler(
        filters.PHOTO, admin_photo
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, admin_text
    ))

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
