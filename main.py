
import os
import json
import base64
import asyncio
import urllib.request
import urllib.error
import logging

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
    ChatJoinRequestHandler,
    ContextTypes,
    filters
)

# =========================
# CONFIG
# =========================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6777943949

MAIN_CHANNEL = "@kinoj90"
STORAGE_CHANNEL = "@kusyi8"
REQUEST_CHANNEL = -1004307552065

REQUEST_LINK = "https://t.me/+lb1ZPri4VWs3ZTUy"

DB_FILE = "movies.json"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPOSITORY = os.getenv(
    "GITHUB_REPOSITORY",
    "khurshed34/kino-bot-new"
)
BRANCH = os.getenv("GITHUB_REF_NAME", "main")

REQUIRED_CHANNELS = [
    {
        "id": "@merlin267",
        "name": "Merlin",
        "url": "https://t.me/merlin267"
    },
    {
        "id": REQUEST_CHANNEL,
        "name": "Канали заявка",
        "url": REQUEST_LINK
    },
    {
        "id": MAIN_CHANNEL,
        "name": "Канали кино",
        "url": "https://t.me/kinoj90"
    }
]

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================
# DATABASE
# =========================

def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            data.setdefault("movies", {})
            data.setdefault("users", [])
            data.setdefault("requests", 0)
            data.setdefault("pending_requests", {})
            return data

    except Exception as error:
        logging.warning("Database load error: %s", error)

    return {
        "movies": {},
        "users": [],
        "requests": 0,
        "pending_requests": {}
    }


db = load_db()


def save_local():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(
            db,
            f,
            ensure_ascii=False,
            indent=2
        )


def github_backup():
    if not GITHUB_TOKEN:
        logging.warning("GITHUB_TOKEN missing")
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
        req = urllib.request.Request(
            url,
            headers=headers
        )

        with urllib.request.urlopen(
            req,
            timeout=30
        ) as response:
            sha = json.loads(
                response.read()
            ).get("sha")

    except urllib.error.HTTPError as error:
        if error.code != 404:
            logging.error("GitHub read error: %s", error)
            return

    content = json.dumps(
        db,
        ensure_ascii=False,
        indent=2
    )

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
        with urllib.request.urlopen(
            req,
            timeout=30
        ) as response:
            logging.info(
                "GitHub backup OK: %s",
                response.status
            )

    except Exception as error:
        logging.error("GitHub backup failed: %s", error)


async def save_database():
    save_local()
    await asyncio.to_thread(github_backup)


# =========================
# ADMIN
# =========================

def is_admin(user_id):
    return user_id == ADMIN_ID


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Иловаи кино",
                callback_data="add"
            )
        ],
        [
            InlineKeyboardButton(
                "🗑 Нест кардани кино",
                callback_data="delete"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Омори бот",
                callback_data="stats"
            )
        ]
    ])


# =========================
# JOIN REQUEST HANDLER
# =========================

async def join_request_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    join_request = update.chat_join_request

    if not join_request:
        return

    if join_request.chat.id != REQUEST_CHANNEL:
        return

    user_id = join_request.from_user.id

    db.setdefault("pending_requests", {})

    db["pending_requests"][str(user_id)] = {
        "chat_id": join_request.chat.id,
        "date": join_request.date.isoformat()
    }

    logging.info(
        "JOIN REQUEST RECEIVED | USER=%s | CHANNEL=%s",
        user_id,
        join_request.chat.id
    )

    await save_database()


# =========================
# APPROVE JOIN REQUEST
# =========================

async def approve_user_request(user_id, context):
    """
    Кӯшиш мекунад заявкаи корбарро қабул кунад.
    Агар корбар аллакай аъзо бошад, санҷиши обуна
    дар функсияи check_subscription иҷро мешавад.
    """

    try:
        result = await context.bot.approve_chat_join_request(
            chat_id=REQUEST_CHANNEL,
            user_id=user_id
        )

        if result:
            db.setdefault("pending_requests", {})
            db["pending_requests"].pop(str(user_id), None)

            logging.info(
                "JOIN REQUEST APPROVED | USER=%s",
                user_id
            )

            await save_database()
            return True, None

        return False, "Telegram заявкаро қабул накард."

    except Exception as error:
        logging.warning(
            "APPROVE REQUEST ERROR | USER=%s | %s",
            user_id,
            error
        )

        return False, str(error)


# =========================
# SUBSCRIPTION CHECK
# =========================

async def check_subscription(user_id, context):
    missing = []
    errors = []

    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(
                chat_id=channel["id"],
                user_id=user_id
            )

            status = member.status

            logging.info(
                "SUB CHECK | USER=%s | CHANNEL=%s | STATUS=%s",
                user_id,
                channel["id"],
                status
            )

            subscribed = status in (
                "member",
                "administrator",
                "creator"
            )

            if status == "restricted":
                subscribed = member.is_member

            if not subscribed:
                missing.append(channel)

        except Exception as error:
            logging.error(
                "SUB CHECK ERROR | CHANNEL=%s | %s",
                channel["id"],
                error
            )

            errors.append({
                "channel": channel,
                "error": str(error)
            })

    return missing, errors


def sub_keyboard(missing):
    buttons = []

    for channel in missing:
        buttons.append([
            InlineKeyboardButton(
                "➕ Обуна: " + channel["name"],
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


# =========================
# SUBSCRIPTION MESSAGE
# =========================

async def show_subscription_status(
    message,
    missing,
    errors
):
    if errors:
        await message.reply_text(
            "⚠️ Бот натавонист обунаро дар баъзе каналҳо санҷад.\n\n"
            "Эҳтимол бот дар яке аз каналҳо админ нест "
            "ё иҷозатҳои зарурӣ надорад.\n\n"
            "Тафсилоти хато дар GitHub Actions Logs сабт шудааст."
        )
        return

    if missing:
        missing_request = any(
            channel["id"] == REQUEST_CHANNEL
            for channel in missing
        )

        names = "\n".join(
            "❌ " + channel["name"]
            for channel in missing
        )

        if missing_request:
            text = (
                "❗ Шумо ҳанӯз ба ҳамаи каналҳо обуна нестед.\n\n"
                f"{names}\n\n"
                "Ба канали заявка дархост фиристед.\n"
                "Баъд ба бот баргашта, тугмаи "
                "«✅ Санҷиши обуна»-ро пахш кунед.\n\n"
                "🤖 Бот кӯшиш мекунад заявкаи шуморо "
                "худаш қабул кунад."
            )
        else:
            text = (
                "❗ Шумо ҳанӯз ба ҳамаи каналҳо обуна нестед.\n\n"
                f"{names}\n\n"
                "Ба каналҳои дар боло нишондодашуда обуна шавед "
                "ва баъд санҷишро пахш кунед."
            )

        await message.reply_text(
            text,
            reply_markup=sub_keyboard(missing)
        )


# =========================
# SEND MOVIE
# =========================

async def send_movie(chat_id, context, code):
    movie = db["movies"].get(str(code))

    if not movie:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Ин кино дар база нест!"
        )
        return

    db["requests"] += 1

    await context.bot.send_video(
        chat_id=chat_id,
        video=movie["file_id"],
        caption=movie.get("title", "🎬 Кино")
    )

    await save_database()


# =========================
# START
# =========================

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
            "🎬 Хуш омадед!\n\n"
            "Барои гирифтани кино тугмаи "
            "«Тамошо»-ро аз канали мо пахш кунед."
        )
        return

    code = context.args[0]
    context.user_data["movie_code"] = code

    missing, errors = await check_subscription(
        user_id,
        context
    )

    if errors or missing:
        await show_subscription_status(
            update.message,
            missing,
            errors
        )
        return

    await send_movie(
        update.effective_chat.id,
        context,
        code
    )


# =========================
# CHECK BUTTON
# =========================

async def check_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    code = context.user_data.get("movie_code")

    if not code:
        await query.message.reply_text(
            "❌ Рамзи кино ёфт нашуд.\n"
            "Аз нав тугмаи Тамошоро пахш кунед."
        )
        return

    # Аввал кӯшиш мекунем заявкаи канали REQUEST-ро қабул кунем.
    approved, approval_error = await approve_user_request(
        user_id,
        context
    )

    if approved:
        await query.message.reply_text(
            "✅ Заявкаи шумо аз тарафи бот қабул шуд!\n"
            "🔎 Акнун обуна санҷида мешавад..."
        )

    # Баъд аз қабул кардан, обунаи ҳамаи каналҳоро месанҷем.
    missing, errors = await check_subscription(
        user_id,
        context
    )

    if errors:
        await show_subscription_status(
            query.message,
            missing,
            errors
        )
        return

    if missing:
        request_missing = any(
            channel["id"] == REQUEST_CHANNEL
            for channel in missing
        )

        if request_missing and not approved:
            logging.warning(
                "REQUEST NOT APPROVED | USER=%s | ERROR=%s",
                user_id,
                approval_error
            )

            await query.message.reply_text(
                "⚠️ Заявкаи шумо қабул карда нашуд.\n\n"
                "Сабабҳои эҳтимолӣ:\n"
                "• Шумо ҳанӯз ба канали заявка дархост нафиристодаед.\n"
                "• Бот иҷозати қабул кардани заявкаро надорад.\n\n"
                "Админ бояд дар канали заявка барои бот "
                "иҷозати «Invite Users»-ро фаъол кунад."
            )

        await show_subscription_status(
            query.message,
            missing,
            errors
        )
        return

    await query.message.reply_text(
        "✅ Обунаи шумо тасдиқ шуд!\n"
        "🎬 Кино фиристода мешавад..."
    )

    await send_movie(
        query.message.chat_id,
        context,
        code
    )


# =========================
# ADMIN BUTTONS
# =========================

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


# =========================
# ADMIN VIDEO
# =========================

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
                "✅ Видео дар канали хусусӣ нигоҳ дошта шуд.\n\n"
                "Акнун номи киноро нависед."
            )

        except Exception as error:
            logging.error("Storage error: %s", error)

            await update.message.reply_text(
                "❌ Видео ба канали хусусӣ фиристода нашуд.\n"
                "Иҷозати администраторро санҷед."
            )

    elif state == "preview":
        context.user_data["preview"] = {
            "type": "video",
            "file_id": update.message.video.file_id
        }

        await publish_movie(update, context)


# =========================
# ADMIN PHOTO
# =========================

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


# =========================
# ADMIN TEXT
# =========================

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
            "🖼 Акнун сурат ё трейлери кӯтоҳ фиристед.\n\n"
            "Агар пешнамоиш лозим набошад, /publish нависед."
        )

    elif state == "delete":
        code = value

        if code in db["movies"]:
            del db["movies"][code]
            await save_database()

            await update.message.reply_text(
                f"✅ Кинои {code} нест карда шуд.",
                reply_markup=admin_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Ин рамз ёфт нашуд."
            )

        context.user_data.clear()


# =========================
# PUBLISH MOVIE
# =========================

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

    numbers = [
        int(x)
        for x in db["movies"]
        if str(x).isdigit()
    ]

    code = str(max(numbers, default=100) + 1)

    bot_info = await context.bot.get_me()

    watch_url = (
        f"https://t.me/{bot_info.username}?start={code}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎬 Тамошо",
                url=watch_url
            )
        ]
    ])

    caption = (
        f"🎬 {title}\n\n"
        f"{description}\n\n"
        f"🔢 Рамзи кино: {code}"
    )

    preview = user_data.get("preview")

    try:
        if preview and preview["type"] == "photo":
            await context.bot.send_photo(
                chat_id=MAIN_CHANNEL,
                photo=preview["file_id"],
                caption=caption,
                reply_markup=keyboard
            )

        elif preview and preview["type"] == "video":
            await context.bot.send_video(
                chat_id=MAIN_CHANNEL,
                video=preview["file_id"],
                caption=caption,
                reply_markup=keyboard
            )

        else:
            await context.bot.send_message(
                chat_id=MAIN_CHANNEL,
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
            "✅ Кино нашр шуд!\n\n"
            f"🎬 {title}\n"
            f"🔢 Рамз: {code}",
            reply_markup=admin_keyboard()
        )

    except Exception as error:
        logging.error("Publish error: %s", error)

        await update.effective_message.reply_text(
            "❌ Нашри кино иҷро нашуд.\n"
            "Иҷозати администраторро санҷед."
        )

    context.user_data.clear()


# =========================
# PUBLISH COMMAND
# =========================

async def publish_command(update, context):
    if not is_admin(update.effective_user.id):
        return

    if context.user_data.get("state") != "preview":
        return

    await publish_movie(update, context)


# =========================
# ADMIN COMMAND
# =========================

async def admin_command(update, context):
    if not is_admin(update.effective_user.id):
        return

    context.user_data.clear()

    await update.message.reply_text(
        "👑 Панели админ",
        reply_markup=admin_keyboard()
    )


# =========================
# CANCEL
# =========================

async def cancel_command(update, context):
    if not is_admin(update.effective_user.id):
        return

    context.user_data.clear()

    await update.message.reply_text(
        "❌ Амалиёт бекор карда шуд.",
        reply_markup=admin_keyboard()
    )


# =========================
# STARTUP
# =========================

async def post_init(app):
    logging.info("KINO BOT STARTED")
    logging.info("Movies loaded: %s", len(db["movies"]))
    logging.info("Request channel: %s", REQUEST_CHANNEL)


# =========================
# MAIN
# =========================

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
    app.add_handler(CommandHandler("cancel", cancel_command))

    # Қабули маълумоти Join Request аз Telegram
    app.add_handler(
        ChatJoinRequestHandler(join_request_handler)
    )

    app.add_handler(
        CallbackQueryHandler(
            check_button,
            pattern="^check$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            admin_buttons,
            pattern="^(add|delete|stats)$"
        )
    )

    app.add_handler(
        MessageHandler(filters.VIDEO, admin_video)
    )

    app.add_handler(
        MessageHandler(filters.PHOTO, admin_photo)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_text
        )
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
