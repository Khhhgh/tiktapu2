
import logging
import re
import os
import asyncio
import yt_dlp
import nest_asyncio
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

nest_asyncio.apply()

BOT_TOKEN = "6012796077:AAE2buse2dGVlymtbXmUcg10gKE87SpvpXQ"
OWNER_ID = 1310488710

# إعداد MongoDB Atlas
MONGO_URL = "mongodb+srv://botthaker:gPFqGj6SsOY692ap@cluster0.ufto3i2.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URL)
db = client["telegram_bot"]
users_col = db["users"]
config_col = db["config"]

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# جلب المستخدمين من القاعدة
def load_users():
    return set(doc["user_id"] for doc in users_col.find())

# حفظ مستخدم جديد (إذا ما موجود)
def save_user(user_id):
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({"user_id": user_id})

# جلب الإعدادات
def load_config():
    config = config_col.find_one({"_id": "config"})
    if config:
        return config
    else:
        default = {"_id": "config", "sub_channels": []}
        config_col.insert_one(default)
        return default

# حفظ الإعدادات
def save_config(config):
    config_col.replace_one({"_id": "config"}, config, upsert=True)

# تحميل بيانات عند بداية التشغيل
users = load_users()
config = load_config()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in users:
        users.add(user_id)
        save_user(user_id)

        await context.bot.send_message(
            OWNER_ID,
            "تم دخول شخص جديد إلى البوت الخاص بك 👾\n"
            "-----------------------\n"
            "• معلومات العضو الجديد .\n\n"
            f"• الاسم : {update.effective_user.full_name}\n"
            f"• معرف : @{update.effective_user.username or 'لايوجد'}\n"
            f"• الايدي : {user_id}\n"
            "-----------------------\n"
            f"• عدد الأعضاء الكلي : {len(users)}"
        )

    sub_channels = config.get("sub_channels", [])
    for channel in sub_channels:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status not in ["member", "creator", "administrator"]:
                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(f"اشترك في {channel}", url=f"https://t.me/{channel.lstrip('@')}")]]
                )
                await update.message.reply_text(
                    f"🔔 عزيزي @{update.effective_user.username or update.effective_user.first_name}\n"
                    "يرجى الاشتراك في القناة التالية أولًا:",
                    reply_markup=keyboard
                )
                return
        except Exception:
            await update.message.reply_text(
                "❌ حدث خطأ في التحقق من الاشتراك. تأكد أن البوت مشرف في القنوات."
            )
            return

    welcome_text = f"""
🌝 أهلاً بك عزيزي @{update.effective_user.username or update.effective_user.first_name}

🍂 هذا البوت يساعدك على تحميل مقاطع الفيديو بسهولة وسرعة.

🍁 أرسل الرابط فقط، وأنا أرسل لك الفيديو مباشرة!
    """
    await update.message.reply_text(welcome_text)

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ أنت لست مالك البوت.")
        return

    keyboard = [
        [InlineKeyboardButton("➕ إضافة قناة اشتراك", callback_data="add_sub_channel")],
        [InlineKeyboardButton("➖ حذف قناة اشتراك", callback_data="del_sub_channel")],
        [InlineKeyboardButton("📢 إرسال إذاعة", callback_data="broadcast")],
        [InlineKeyboardButton("📊 عرض الإحصائيات", callback_data="stats")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("لوحة الأدمن:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id != OWNER_ID:
        await query.edit_message_text("❌ أنت لست مالك البوت.")
        return

    data = query.data

    if data == "add_sub_channel":
        await query.edit_message_text("أرسل معرف القناة لإضافتها (مثلاً @channelusername):")
        context.user_data["action"] = "add_sub_channel"

    elif data == "del_sub_channel":
        sub_channels = config.get("sub_channels", [])
        if not sub_channels:
            await query.edit_message_text("لا توجد قنوات مضافة حالياً.")
            return
        buttons = [
            [InlineKeyboardButton(ch, callback_data=f"del_chan|{ch}")]
            for ch in sub_channels
        ]
        buttons.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")])
        await query.edit_message_text("اختر قناة للحذف:", reply_markup=InlineKeyboardMarkup(buttons))
        context.user_data["action"] = None

    elif data.startswith("del_chan|"):
        channel_to_del = data.split("|",1)[1]
        sub_channels = config.get("sub_channels", [])
        if channel_to_del in sub_channels:
            sub_channels.remove(channel_to_del)
            config["sub_channels"] = sub_channels
            save_config(config)
            await query.edit_message_text(f"تم حذف القناة {channel_to_del}")
        else:
            await query.edit_message_text("القناة غير موجودة.")

    elif data == "broadcast":
        await query.edit_message_text("أرسل الآن نص الإذاعة:")
        context.user_data["action"] = "broadcast"

    elif data == "stats":
        await query.edit_message_text(f"عدد المستخدمين: {len(users)}")

    elif data == "admin_back":
        await admin(update, context)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in users:
        users.add(user_id)
        save_user(user_id)

    action = context.user_data.get("action")

    if action == "add_sub_channel":
        if not text.startswith("@"):
            await update.message.reply_text("❌ يجب أن يبدأ معرف القناة بـ @")
            return
        sub_channels = config.get("sub_channels", [])
        if text in sub_channels:
            await update.message.reply_text("❌ القناة مضافة سابقاً.")
            return
        sub_channels.append(text)
        config["sub_channels"] = sub_channels
        save_config(config)
        context.user_data["action"] = None
        await update.message.reply_text(f"✅ تم إضافة قناة الاشتراك: {text}")

    elif action == "broadcast":
        count = 0
        for uid in users:
            try:
                await context.bot.send_message(chat_id=uid, text=text)
                count += 1
            except Exception:
                pass
        context.user_data["action"] = None
        await update.message.reply_text(f"✅ تم إرسال الإذاعة إلى {count} مستخدم.")

    else:
        url_pattern = r"(https?://[^\s]+)"
        urls = re.findall(url_pattern, text)
        if urls:
            await update.message.reply_text("⏳ انتظر قليلًا 🥀..")
            video_url = urls[0]

            ydl_opts = {
                "format": "mp4",
                "outtmpl": "downloaded_video.%(ext)s",
                "quiet": True,
                "no_warnings": True,
                "http_timeout": 180,
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])
                video_path = "downloaded_video.mp4"

                if os.path.exists(video_path):
                    with open(video_path, "rb") as video_file:
                        await update.message.reply_video(video_file)
                    os.remove(video_path)
                else:
                    await update.message.reply_text("❌ لم أتمكن من تحميل الفيديو.")
            except Exception as e:
                await update.message.reply_text(f"❌ حدث خطأ أثناء تحميل الفيديو.\n{e}")

async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))

    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
