import os
import json
import base64
import asyncio
import logging
import urllib.request
import urllib.error

from datetime import datetime, timezone, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ChatJoinRequestHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6777943949

MAIN_CHANNEL = "@kinoj90"
STORAGE_CHANNEL = "@kusyi8"
REQUEST_CHANNEL = -1004307552065

REQUEST_LINK = "https://t.me/+lb1ZPri4VWs3ZTUy"
INSTAGRAM_URL = "https://www.instagram.com/dunyo.kino90/"

DB_FILE = "movies.json"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPOSITORY = os.getenv("GITHUB_REPOSITORY", "khurshed34/kino-bot-new")
BRANCH = os.getenv("GITHUB_REF_NAME", "main")

DUSHANBE_TZ = timezone(timedelta(hours=5))
SCHEDULER_INTERVAL = 15

REQUIRED_CHANNELS = [
    {
        "id": "@merlin267",
        "name": "Merlin",
        "url": "https://t.me/merlin267",
    },
    {
        "id": REQUEST_CHANNEL,
        "name": "Канали заявка",
        "url": REQUEST_LINK,
    },
    {
        "id": MAIN_CHANNEL,
        "name": "Канали кино",
        "url": "https://t.me/kinoj90",
    },
]

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# =========================================================
# DATABASE
# =========================================================

def load_db():
    default = {
        "movies": {},
        "users": [],
        "requests": 0,
        "pending_requests": {},
        "request_users": [],
        "instagram_confirmed": [],
        "joined_at": {},
        "last_active": {},
        "posts": {},
        "next_post_id": 1,
    }

    try:
        with open(DB_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return default

        for key, value in default.items():
            data.setdefault(key, value)

        data["users"] = list(set(int(x) for x in data.get("users", [])))
        data["request_users"] = list(
            set(int(x) for x in data.get("request_users", []))
        )
        data["instagram_confirmed"] = list(
            set(int(x) for x in data.get("instagram_confirmed", []))
        )

        if not isinstance(data["movies"], dict):
            data["movies"] = {}
        if not isinstance(data["pending_requests"], dict):
            data["pending_requests"] = {}
        if not isinstance(data["posts"], dict):
            data["posts"] = {}

        return data

    except FileNotFoundError:
        return default
    except Exception:
        logging.exception("Database load error")
        return default


db = load_db()


def save_local():
    temporary_file = DB_FILE + ".tmp"
    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(db, file, ensure_ascii=False, indent=2)
    os.replace(temporary_file, DB_FILE)


def github_backup():
    if not GITHUB_TOKEN:
        logging.warning("GITHUB_TOKEN missing; local database only")
        return

    api_url = (
        f"https://api.github.com/repos/{REPOSITORY}"
        f"/contents/{DB_FILE}?ref={BRANCH}"
    )
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    sha = None
    try:
        request = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            sha = json.loads(response.read()).get("sha")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            logging.error("GitHub database read failed: %s", error)
            return
    except Exception:
        logging.exception("GitHub database read failed")
        return

    content = json.dumps(db, ensure_ascii=False, indent=2)
    payload = {
        "message": "Update Kino Bot database",
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    request = urllib.request.Request(
        api_url.split("?")[0],
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="PUT",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            logging.info("GitHub backup OK: %s", response.status)
    except Exception:
        logging.exception("GitHub backup failed")


async def save_database():
    try:
        save_local()
        await asyncio.to_thread(github_backup)
    except Exception:
        logging.exception("Save database error")


def add_user(user_id):
    user_id = int(user_id)
    now = datetime.now(DUSHANBE_TZ).isoformat()

    if user_id not in db["users"]:
        db["users"].append(user_id)
        db["joined_at"][str(user_id)] = now

    db["last_active"][str(user_id)] = now


# =========================================================
# KEYBOARDS
# =========================================================

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Иловаи кино", callback_data="movie_add")],
        [InlineKeyboardButton("🗑 Нест кардани кино", callback_data="movie_delete")],
        [InlineKeyboardButton("📢 Пост гузоштан", callback_data="post_add")],
        [InlineKeyboardButton("⏰ Пости вақтдор", callback_data="post_schedule")],
        [InlineKeyboardButton("🗑 Нест кардани пост", callback_data="post_delete")],
        [InlineKeyboardButton("📊 Омори бот", callback_data="stats")],
    ])


def is_admin(user_id):
    return int(user_id) == ADMIN_ID


def subscription_keyboard(missing, user_id):
    buttons = []

    for channel in missing:
        buttons.append([
            InlineKeyboardButton(
                "➕ Обуна: " + channel["name"],
                url=channel["url"],
            )
        ])

    # Instagram API барои санҷидани follow-и ҳар корбари одӣ
    # endpoint-и боэътимоди умумӣ намедиҳад. Ин тугма танҳо
    # эъломияи худи корбарро сабт мекунад, на санҷиши воқеиро.
    if user_id not in db["instagram_confirmed"]:
        buttons.append([
            InlineKeyboardButton("📸 Обуна ба Instagram", url=INSTAGRAM_URL)
        ])
        buttons.append([
            InlineKeyboardButton(
                "✅ Ман обуна шудам",
                callback_data="instagram_confirm",
            )
        ])

    buttons.append([
        InlineKeyboardButton("🔄 Санҷиши обуна", callback_data="check")
    ])
    return InlineKeyboardMarkup(buttons)


# =========================================================
# SUBSCRIPTION
# =========================================================

async def check_subscription(user_id, context):
    missing = []
    errors = []
    user_key = str(user_id)

    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(
                chat_id=channel["id"],
                user_id=user_id,
            )

            status = member.status
            subscribed = status in ("member", "administrator", "creator")

            if status == "restricted":
                subscribed = bool(getattr(member, "is_member", False))

            if not subscribed:
                # Дархости фиристодашуда ба канали заявка ҳамчун
                # иҷрои шарти дархост ҳисоб мешавад. Агар қабул шуда
                # бошад, get_chat_member онро ҳамчун member мебинад.
                if (
                    channel["id"] == REQUEST_CHANNEL
                    and user_key in db["pending_requests"]
                ):
                    continue
                missing.append(channel)

        except Exception as error:
            # Агар get_chat_member барои канали заявка ҳанӯз member
            # нишон надиҳад, аммо join request-и воқеӣ сабт шуда бошад,
            # ин шарт иҷрошуда ҳисоб мешавад.
            if (
                channel["id"] == REQUEST_CHANNEL
                and user_key in db["pending_requests"]
            ):
                continue

            logging.error(
                "SUB CHECK ERROR | CHANNEL=%s | %s",
                channel["id"],
                error,
            )
            errors.append({"channel": channel, "error": str(error)})

    return missing, errors


async def show_subscription_status(message, missing, errors, user_id):
    telegram_missing = "\n".join("❌ " + channel["name"] for channel in missing)
    instagram_missing = user_id not in db["instagram_confirmed"]

    text = "🎬 Барои дастрасӣ ба кино шартҳои зеринро иҷро кунед:\n\n"
    if telegram_missing:
        text += telegram_missing + "\n"
    if instagram_missing:
        text += "❌ Instagram: @dunyo.kino90\n"

    if errors:
        text += (
            "\n⚠️ Баъзе каналҳоро санҷида натавонистам. "
            "Иҷозати администратори ботро дар каналҳо санҷед."
        )
    else:
        text += "\nПас аз иҷрои шартҳо «Санҷиши обуна»-ро пахш кунед."

    text += (
        "\n\nЭзоҳ: Instagram-ро бот мустақим санҷида наметавонад; "
        "тугмаи тасдиқ танҳо изҳороти корбарро сабт мекунад."
    )

    await message.reply_text(
        text,
        reply_markup=subscription_keyboard(missing, user_id),
    )


# =========================================================
# JOIN REQUEST HANDLER
# =========================================================

async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_request = update.chat_join_request
    if not join_request or join_request.chat.id != REQUEST_CHANNEL:
        return

    user_id = int(join_request.from_user.id)
    user_key = str(user_id)

    add_user(user_id)
    if user_id not in db["request_users"]:
        db["request_users"].append(user_id)

    db["pending_requests"][user_key] = {
        "chat_id": join_request.chat.id,
        "date": join_request.date.isoformat(),
        "status": "pending",
    }

    logging.info("JOIN REQUEST SAVED | USER=%s", user_id)
    await save_database()

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "📩 Дархости нави обуна ба канали заявка!\n\n"
                f"👤 User ID: {user_id}\n"
                f"📊 Дархосткунандагон: {len(db['request_users'])}"
            ),
        )
    except Exception:
        logging.exception("Admin notification failed")


# =========================================================
# MOVIES
# =========================================================

async def send_movie(chat_id, context, code):
    movie = db["movies"].get(str(code))
    if not movie:
        await context.bot.send_message(chat_id, "❌ Ин кино дар база нест!")
        return

    await context.bot.send_video(
        chat_id=chat_id,
        video=movie["file_id"],
        caption=movie.get("title", "🎬 Кино"),
    )
    db["requests"] += 1
    await save_database()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    add_user(user_id)
    await save_database()

    if is_admin(user_id) and not context.args:
        await update.message.reply_text(
            "👑 Панели админ",
            reply_markup=admin_keyboard(),
        )
        return

    if not context.args:
        await update.message.reply_text(
            "🎬 Хуш омадед!\n\n"
            "Барои гирифтани кино тугмаи «Тамошо»-ро аз канали мо пахш кунед."
        )
        return

    code = context.args[0]
    context.user_data["movie_code"] = code

    missing, errors = await check_subscription(user_id, context)
    instagram_ok = user_id in db["instagram_confirmed"]

    if errors or missing or not instagram_ok:
        await show_subscription_status(
            update.message, missing, errors, user_id
        )
        return

    await send_movie(update.effective_chat.id, context, code)


async def instagram_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in db["instagram_confirmed"]:
        db["instagram_confirmed"].append(user_id)
        await save_database()

    code = context.user_data.get("movie_code")
    if not code:
        await query.message.reply_text(
            "✅ Тасдиқи шумо сабт шуд. Барои гирифтани кино тугмаи «Тамошо»-ро пахш кунед."
        )
        return

    missing, errors = await check_subscription(user_id, context)
    if errors or missing:
        await show_subscription_status(query.message, missing, errors, user_id)
        return

    await send_movie(query.message.chat_id, context, code)


async def check_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    code = context.user_data.get("movie_code")

    if not code:
        await query.message.reply_text(
            "❌ Рамзи кино ёфт нашуд. Аз нав тугмаи «Тамошо»-ро пахш кунед."
        )
        return

    missing, errors = await check_subscription(user_id, context)
    instagram_ok = user_id in db["instagram_confirmed"]

    if errors or missing or not instagram_ok:
        await show_subscription_status(query.message, missing, errors, user_id)
        return

    await send_movie(query.message.chat_id, context, code)


# =========================================================
# ADMIN STATS
# =========================================================

async def calculate_stats(context):
    users = list(set(db["users"]))
    semaphore = asyncio.Semaphore(3)

    async def check_one(user_id):
        async with semaphore:
            return await check_subscription(user_id, context)

    results = await asyncio.gather(
        *(check_one(user_id) for user_id in users),
        return_exceptions=True,
    )

    telegram_ok = 0
    unknown = 0
    complete = 0

    for user_id, result in zip(users, results):
        if isinstance(result, Exception):
            unknown += 1
            continue

        missing, errors = result
        if errors:
            unknown += 1
        elif not missing:
            telegram_ok += 1
            if user_id in db["instagram_confirmed"]:
                complete += 1

    today = datetime.now(DUSHANBE_TZ).date()
    new_today = 0
    active_today = 0

    for user_id in users:
        joined = db["joined_at"].get(str(user_id))
        active = db["last_active"].get(str(user_id))
        try:
            if joined and datetime.fromisoformat(joined).date() == today:
                new_today += 1
            if active and datetime.fromisoformat(active).date() == today:
                active_today += 1
        except Exception:
            pass

    all_users = set(db["users"]) | set(db["request_users"])

    return {
        "total": len(all_users),
        "started_users": len(set(db["users"])),
        "request_users": len(set(db["request_users"])),
        "telegram": telegram_ok,
        "instagram": len(set(db["instagram_confirmed"]) & set(users)),
        "complete": complete,
        "incomplete": max(0, len(users) - complete),
        "unknown": unknown,
        "new_today": new_today,
        "active_today": active_today,
        "movies": len(db["movies"]),
        "requests": db["requests"],
        "posts": len(db["posts"]),
        "scheduled": sum(
            1 for post in db["posts"].values()
            if post.get("status") == "scheduled"
        ),
    }


# =========================================================
# POST MANAGEMENT
# =========================================================

def next_post_id():
    post_id = int(db.get("next_post_id", 1))
    db["next_post_id"] = post_id + 1
    return str(post_id)


async def publish_post_to_channel(context, post):
    chat_id = MAIN_CHANNEL
    post_type = post.get("type")

    if post_type == "photo":
        sent = await context.bot.send_photo(
            chat_id=chat_id,
            photo=post["file_id"],
            caption=post.get("caption", ""),
        )
    elif post_type == "video":
        sent = await context.bot.send_video(
            chat_id=chat_id,
            video=post["file_id"],
            caption=post.get("caption", ""),
        )
    else:
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=post.get("text", ""),
        )

    post["message_id"] = sent.message_id
    post["status"] = "published"
    post["published_at"] = datetime.now(DUSHANBE_TZ).isoformat()
    await save_database()
    return sent


async def scheduler_loop(app: Application):
    logging.info("Post scheduler started")
    while True:
        try:
            now = datetime.now(DUSHANBE_TZ)
            due_posts = []

            for post_id, post in list(db["posts"].items()):
                if post.get("status") != "scheduled":
                    continue
                try:
                    publish_at = datetime.fromisoformat(post["publish_at"])
                    if publish_at.tzinfo is None:
                        publish_at = publish_at.replace(tzinfo=DUSHANBE_TZ)
                    if publish_at <= now:
                        due_posts.append((post_id, post))
                except Exception:
                    logging.exception("Invalid scheduled post time: %s", post_id)

            for post_id, post in due_posts:
                try:
                    await publish_post_to_channel(app, post)
                    logging.info("Scheduled post published: %s", post_id)
                except Exception:
                    logging.exception("Scheduled post failed: %s", post_id)
                    post["status"] = "failed"
                    await save_database()

        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Scheduler error")

        await asyncio.sleep(SCHEDULER_INTERVAL)


async def begin_post(update: Update, context: ContextTypes.DEFAULT_TYPE, scheduled=False):
    context.user_data.clear()
    context.user_data["state"] = "post_content"
    context.user_data["post_scheduled"] = scheduled

    if scheduled:
        await update.callback_query.message.reply_text(
            "⏰ Вақти нашрро бо формати зерин фиристед:\n"
            "2026-12-01 18:30\n\n"
            "Вақт аз рӯи Душанбе (UTC+5) аст."
        )
        context.user_data["state"] = "post_time"
    else:
        await update.callback_query.message.reply_text(
            "📢 Матн, сурат ё видеои постро фиристед.\n"
            "Пост фавран дар канали @kinoj90 нашр мешавад."
        )


async def save_post_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    post = {}

    if message.photo:
        post = {
            "type": "photo",
            "file_id": message.photo[-1].file_id,
            "caption": message.caption or "",
        }
    elif message.video:
        post = {
            "type": "video",
            "file_id": message.video.file_id,
            "caption": message.caption or "",
        }
    elif message.text:
        post = {
            "type": "text",
            "text": message.text,
        }
    else:
        await message.reply_text("❌ Танҳо матн, сурат ё видео фиристед.")
        return

    post_id = next_post_id()
    post["created_at"] = datetime.now(DUSHANBE_TZ).isoformat()

    if context.user_data.get("post_scheduled"):
        post["status"] = "scheduled"
        post["publish_at"] = context.user_data["publish_at"]
        db["posts"][post_id] = post
        await save_database()
        await message.reply_text(
            "✅ Пост барои вақти интихобшуда сабт шуд.\n"
            f"🆔 Рамзи пост: {post_id}\n"
            f"⏰ Вақт: {post['publish_at']}",
            reply_markup=admin_keyboard(),
        )
    else:
        db["posts"][post_id] = post
        try:
            await publish_post_to_channel(context, db["posts"][post_id])
            await message.reply_text(
                "✅ Пост дар канал нашр шуд!\n"
                f"🆔 Рамзи пост: {post_id}",
                reply_markup=admin_keyboard(),
            )
        except Exception as error:
            logging.exception("Post publish error")
            db["posts"].pop(post_id, None)
            await save_database()
            await message.reply_text(
                "❌ Пост нашр нашуд. Ботро дар @kinoj90 администратор кунед.\n"
                f"Хато: {error}"
            )

    context.user_data.clear()


async def delete_post_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: str):
    post = db["posts"].get(str(post_id))
    if not post:
        await update.effective_message.reply_text("❌ Ин рамзи пост ёфт нашуд.")
        return

    if post.get("status") == "published" and post.get("message_id"):
        try:
            await context.bot.delete_message(
                chat_id=MAIN_CHANNEL,
                message_id=post["message_id"],
            )
        except Exception as error:
            await update.effective_message.reply_text(
                "⚠️ Пост аз база хориҷ карда мешавад, аммо аз канал пок нашуд.\n"
                "Иҷозати Delete Messages-и ботро санҷед.\n"
                f"Хато: {error}"
            )
            return

    # Пост аз база низ нест мешавад; агар он пости вақтдор бошад,
    # scheduler дигар онро нашр намекунад.
    del db["posts"][str(post_id)]
    await save_database()
    await update.effective_message.reply_text(
        f"✅ Пост {post_id} аз канал ва базаи бот пок карда шуд.",
        reply_markup=admin_keyboard(),
    )


# =========================================================
# ADMIN CALLBACKS
# =========================================================

async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    action = query.data

    if action == "movie_add":
        context.user_data.clear()
        context.user_data["state"] = "full_video"
        await query.message.reply_text("📹 Видеои пурраи киноро фиристед.")

    elif action == "movie_delete":
        context.user_data.clear()
        context.user_data["state"] = "delete_movie"
        await query.message.reply_text("Рамзи киноеро, ки нест кардан мехоҳед, фиристед.")

    elif action == "post_add":
        await begin_post(update, context, scheduled=False)

    elif action == "post_schedule":
        await begin_post(update, context, scheduled=True)

    elif action == "post_delete":
        context.user_data.clear()
        context.user_data["state"] = "delete_post"
        await query.message.reply_text(
            "🗑 Рамзи постро фиристед.\n"
            "Рамзро баъди нашр бот ба шумо нишон медиҳад."
        )

    elif action == "stats":
        await query.message.reply_text("⏳ Омори бот ҳисоб карда мешавад...")
        stats = await calculate_stats(context)

        text = (
            "📊 ОМОРИ БОТ\n\n"
            f"👥 Ҳамагӣ корбарони сабтшуда: {stats['total']}\n"
            f"🤖 Оғозкардагони бот: {stats['started_users']}\n"
            f"📩 Дархосткунандагони канал: {stats['request_users']}\n\n"
            f"✅ Telegram: {stats['telegram']}\n"
            f"📸 Instagram (эъломияи корбар): {stats['instagram']}\n"
            f"🏆 Шартҳои сабтшуда пурра: {stats['complete']}\n"
            f"❌ Шартҳо пурра нестанд: {stats['incomplete']}\n"
            f"⚠️ Санҷида нашуданд: {stats['unknown']}\n\n"
            f"🆕 Нав имрӯз: {stats['new_today']}\n"
            f"🟢 Фаъол имрӯз: {stats['active_today']}\n\n"
            f"🎬 Киноҳо: {stats['movies']}\n"
            f"📢 Постҳо: {stats['posts']}\n"
            f"⏰ Постҳои интизор: {stats['scheduled']}\n"
            f"🔎 Дархостҳои кино: {stats['requests']}\n\n"
            "ℹ️ Instagram-ро API-и умумӣ мустақим санҷида наметавонад."
        )
        await query.message.reply_text(text, reply_markup=admin_keyboard())


# =========================================================
# ADMIN MOVIE HANDLERS
# =========================================================

async def admin_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    state = context.user_data.get("state")

    if state == "full_video":
        try:
            forwarded = await context.bot.forward_message(
                chat_id=STORAGE_CHANNEL,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
            )
            if not forwarded.video:
                await update.message.reply_text("❌ Видеоро ҳамчун видео фиристед.")
                return

            context.user_data["pending_file_id"] = forwarded.video.file_id
            context.user_data["state"] = "title"
            await update.message.reply_text(
                "✅ Видео дар канали нигоҳдорӣ сабт шуд.\nАкнун номи киноро нависед."
            )
        except Exception:
            logging.exception("Storage forward failed")
            await update.message.reply_text(
                "❌ Видео ба канали нигоҳдорӣ фиристода нашуд. "
                "Иҷозати администраторро санҷед."
            )

    elif state == "preview":
        context.user_data["preview"] = {
            "type": "video",
            "file_id": update.message.video.file_id,
        }
        await publish_movie(update, context)

    elif state == "post_content":
        await save_post_content(update, context)


async def admin_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    state = context.user_data.get("state")

    if state == "preview":
        context.user_data["preview"] = {
            "type": "photo",
            "file_id": update.message.photo[-1].file_id,
        }
        await publish_movie(update, context)

    elif state == "post_content":
        await save_post_content(update, context)


async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    state = context.user_data.get("state")
    value = (update.message.text or "").strip()

    if state == "post_content":
        await save_post_content(update, context)
        return

    if state == "post_time":
        try:
            publish_at = datetime.strptime(value, "%Y-%m-%d %H:%M")
            publish_at = publish_at.replace(tzinfo=DUSHANBE_TZ)

            if publish_at <= datetime.now(DUSHANBE_TZ):
                await update.message.reply_text("❌ Вақт бояд дар оянда бошад. Аз нав фиристед.")
                return

            context.user_data["publish_at"] = publish_at.isoformat()
            context.user_data["state"] = "post_content"
            await update.message.reply_text(
                "✅ Вақт қабул шуд.\nАкнун матн, сурат ё видеои постро фиристед."
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Формат нодуруст аст.\nМисол: 2026-12-01 18:30"
            )
        return

    if state == "delete_post":
        await delete_post_by_id(update, context, value)
        context.user_data.clear()
        return

    if state == "title":
        context.user_data["title"] = value
        context.user_data["state"] = "description"
        await update.message.reply_text("📝 Маълумоти кӯтоҳ дар бораи кино нависед.")
        return

    if state == "description":
        context.user_data["description"] = value
        context.user_data["state"] = "preview"
        await update.message.reply_text(
            "🖼 Сурат ё трейлери кӯтоҳ фиристед.\n"
            "Агар пешнамоиш лозим набошад, /publish нависед."
        )
        return

    if state == "delete_movie":
        code = value
        movie = db["movies"].get(code)
        if not movie:
            await update.message.reply_text("❌ Ин рамзи кино ёфт нашуд.")
        else:
            channel_message_id = movie.get("channel_message_id")
            if channel_message_id:
                try:
                    await context.bot.delete_message(
                        chat_id=MAIN_CHANNEL,
                        message_id=channel_message_id,
                    )
                except Exception:
                    logging.exception("Could not delete movie channel post")

            del db["movies"][code]
            await save_database()
            await update.message.reply_text(
                f"✅ Кинои {code} аз базаи бот пок шуд.",
                reply_markup=admin_keyboard(),
            )
        context.user_data.clear()


async def publish_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    file_id = user_data.get("pending_file_id")
    title = user_data.get("title")
    description = user_data.get("description")

    if not file_id or not title or not description:
        await update.effective_message.reply_text("❌ Маълумот пурра нест.")
        return

    numbers = [int(x) for x in db["movies"] if str(x).isdigit()]
    code = str(max(numbers, default=100) + 1)

    bot_info = await context.bot.get_me()
    watch_url = f"https://t.me/{bot_info.username}?start={code}"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎬 Тамошо", url=watch_url)
    ]])

    caption = f"🎬 {title}\n\n{description}\n\n🔢 Рамзи кино: {code}"
    preview = user_data.get("preview")

    try:
        if preview and preview["type"] == "photo":
            sent = await context.bot.send_photo(
                chat_id=MAIN_CHANNEL,
                photo=preview["file_id"],
                caption=caption,
                reply_markup=keyboard,
            )
        elif preview and preview["type"] == "video":
            sent = await context.bot.send_video(
                chat_id=MAIN_CHANNEL,
                video=preview["file_id"],
                caption=caption,
                reply_markup=keyboard,
            )
        else:
            sent = await context.bot.send_message(
                chat_id=MAIN_CHANNEL,
                text=caption,
                reply_markup=keyboard,
            )

        db["movies"][code] = {
            "file_id": file_id,
            "title": title,
            "description": description,
            "channel_message_id": sent.message_id,
        }
        await save_database()

        await update.effective_message.reply_text(
            f"✅ Кино нашр шуд!\n🎬 {title}\n🔢 Рамз: {code}",
            reply_markup=admin_keyboard(),
        )
    except Exception:
        logging.exception("Movie publish failed")
        await update.effective_message.reply_text(
            "❌ Нашри кино иҷро нашуд. Иҷозати администраторро санҷед."
        )

    context.user_data.clear()


# =========================================================
# COMMANDS
# =========================================================

async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if context.user_data.get("state") != "preview":
        return
    await publish_movie(update, context)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    context.user_data.clear()
    await update.message.reply_text("👑 Панели админ", reply_markup=admin_keyboard())


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Амалиёт бекор карда шуд.",
        reply_markup=admin_keyboard(),
    )


# =========================================================
# STARTUP / MAIN
# =========================================================

async def post_init(app: Application):
    logging.info("KINO BOT STARTED")
    logging.info("Movies loaded: %s", len(db["movies"]))
    logging.info("Users loaded: %s", len(db["users"]))
    logging.info("Saved join requests: %s", len(db["pending_requests"]))
    logging.info("Posts loaded: %s", len(db["posts"]))
    app.create_task(scheduler_loop(app))


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

    app.add_handler(ChatJoinRequestHandler(join_request_handler))

    app.add_handler(CallbackQueryHandler(check_button, pattern="^check$"))
    app.add_handler(
        CallbackQueryHandler(
            instagram_confirm,
            pattern="^instagram_confirm$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            admin_buttons,
            pattern="^(movie_add|movie_delete|post_add|post_schedule|post_delete|stats)$",
        )
    )

    app.add_handler(MessageHandler(filters.VIDEO, admin_video))
    app.add_handler(MessageHandler(filters.PHOTO, admin_photo))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text)
    )

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
