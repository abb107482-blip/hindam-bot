#!/usr/bin/env python3
import os, io, re, json, logging, asyncio, tempfile
from datetime import datetime
from pathlib import Path

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "0").split(",") if x.strip().isdigit()]
MAX_FILE_MB = 45

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, BotCommand
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
    from telegram.constants import ParseMode, ChatAction
    from telegram.error import TelegramError
except ImportError:
    raise SystemExit("pip install python-telegram-bot[all]")

try:
    import yt_dlp
    YT = True
except ImportError:
    YT = False

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ExifTags
    PIL = True
except ImportError:
    PIL = False

try:
    import anthropic
    AI = True
except ImportError:
    AI = False

DB = Path("db.json")

def load():
    if DB.exists():
        return json.loads(DB.read_text("utf-8"))
    return {"users": {}, "stats": {"req": 0, "dl": 0, "img": 0, "q": 0}}

def save(d):
    DB.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")

def udata(d, uid):
    k = str(uid)
    if k not in d["users"]:
        d["users"][k] = {"req": 0, "dl": 0, "img": 0, "q": 0, "joined": datetime.now().isoformat()}
    return d["users"][k]

history = {}

async def ask_ai(uid, msg):
    if not AI or not ANTHROPIC_KEY:
        return fallback(msg)
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        if uid not in history:
            history[uid] = []
        history[uid].append({"role": "user", "content": msg})
        if len(history[uid]) > 20:
            history[uid] = history[uid][-20:]
        r = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1500,
            system="anta mosaed bot telegram thaki wasmak hindam. ajeb bel3arabiya beshakl wadod maa emoji monaseba.",
            messages=history[uid]
        )
        ans = r.content[0].text
        history[uid].append({"role": "assistant", "content": ans})
        return ans
    except Exception as e:
        log.error("AI error: %s", e)
        return fallback(msg)

def fallback(t):
    t = t.lower()
    if any(w in t for w in ["mrhba", "hai", "salam", "ahla", "hla", "hi", "hello"]):
        return "ahlan! ana hindam 🤖\nkayf aqdar asa3dak?"
    if any(w in t for w in ["shkra", "shkran", "mnnon", "thank"]):
        return "al3afw! dayman fy khdmtak 😊"
    return "aktb so2alak wasa2jibak, aw aktb /help lel mosa3ada."

def vid_info(url):
    if not YT:
        return None
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "no_warnings": True}) as y:
            return y.extract_info(url, download=False)
    except:
        return None

def do_download(url, out, audio=False):
    if not YT:
        return None, "yt-dlp not installed"
    try:
        opts = {"quiet": True, "no_warnings": True, "outtmpl": os.path.join(out, "%(title)s.%(ext)s")}
        if audio:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
        else:
            opts["format"] = "best[filesize<50M]/best"
            opts["merge_output_format"] = "mp4"
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])
        files = list(Path(out).iterdir())
        return str(files[0]) if files else None, ""
    except Exception as e:
        return None, str(e)[:150]

MODES = {
    "enhance": "tahsin shaml",
    "sharpen": "tahdid hawaf",
    "hdr": "HDR",
    "vintage": "qadim",
    "grayscale": "abyad waswad",
    "denoise": "izalat dawda",
    "upscale": "raf3 aldaqa x2",
    "vivid": "alwan zahya",
}

def process_img(data, mode):
    if not PIL:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        try:
            for tag, val in (img._getexif() or {}).items():
                if ExifTags.TAGS.get(tag) == "Orientation":
                    img = img.rotate({3: 180, 6: 270, 8: 90}.get(val, 0), expand=True)
                    break
        except:
            pass
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if mode == "enhance":
            img = ImageEnhance.Brightness(img).enhance(1.1)
            img = ImageEnhance.Contrast(img).enhance(1.2)
            img = ImageEnhance.Sharpness(img).enhance(2.0)
            img = ImageEnhance.Color(img).enhance(1.15)
        elif mode == "sharpen":
            img = img.filter(ImageFilter.UnsharpMask(2, 150, 3))
            img = ImageEnhance.Sharpness(img).enhance(3.0)
        elif mode == "hdr":
            img = ImageEnhance.Contrast(img).enhance(1.7)
            img = ImageEnhance.Color(img).enhance(1.5)
            img = ImageEnhance.Brightness(img).enhance(1.05)
        elif mode == "vintage":
            img = ImageEnhance.Color(img).enhance(0.5)
            img = ImageEnhance.Brightness(img).enhance(0.88)
            img = ImageEnhance.Contrast(img).enhance(1.3)
        elif mode == "grayscale":
            img = ImageOps.grayscale(img)
            img = ImageEnhance.Contrast(img).enhance(1.4)
        elif mode == "denoise":
            img = img.filter(ImageFilter.MedianFilter(3))
            img = ImageEnhance.Sharpness(img).enhance(1.5)
        elif mode == "upscale":
            img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        elif mode == "vivid":
            img = ImageEnhance.Color(img).enhance(1.8)
            img = ImageEnhance.Contrast(img).enhance(1.3)
        out = io.BytesIO()
        fmt = "JPEG" if img.mode == "RGB" else "PNG"
        img.save(out, fmt, quality=95, optimize=True)
        return out.getvalue()
    except Exception as e:
        log.error("img error: %s", e)
        return None

def main_kb():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📥 Video"), KeyboardButton("🎵 Audio")],
        [KeyboardButton("🖼 Image"), KeyboardButton("🧠 AI Question")],
        [KeyboardButton("📊 Stats"), KeyboardButton("ℹ️ Help")],
    ], resize_keyboard=True)

def img_kb(fid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ Enhance", callback_data="i_enhance_" + fid),
         InlineKeyboardButton("🌈 HDR", callback_data="i_hdr_" + fid)],
        [InlineKeyboardButton("🔍 Sharpen", callback_data="i_sharpen_" + fid),
         InlineKeyboardButton("🎨 Vivid", callback_data="i_vivid_" + fid)],
        [InlineKeyboardButton("🎞 Vintage", callback_data="i_vintage_" + fid),
         InlineKeyboardButton("⬛ Grayscale", callback_data="i_grayscale_" + fid)],
        [InlineKeyboardButton("🔵 Denoise", callback_data="i_denoise_" + fid),
         InlineKeyboardButton("⬆️ Upscale", callback_data="i_upscale_" + fid)],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

def dl_kb(url):
    k = url[-30:]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Video MP4", callback_data="dv_" + k)],
        [InlineKeyboardButton("🎵 Audio MP3", callback_data="da_" + k)],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

async def cmd_start(u, c):
    d = load()
    udata(d, u.effective_user.id)
    save(d)
    name = u.effective_user.first_name
    await u.message.reply_text(
        "🌟 Ahlan " + name + "!\n\n"
        "Ana Hindam - botuk althaki 🤖\n\n"
        "📥 Tahmil video wa sawt\n"
        "🖼 Tahsin alsor b 8 taathirat\n"
        "🧠 Ijabat alasilat bil AI\n\n"
        "💡 Arsel rabat video, sora, aw aktb so2alak!",
        reply_markup=main_kb()
    )

async def cmd_help(u, c):
    await u.message.reply_text(
        "📖 Dalil alasti3mal\n\n"
        "📥 Arsel rabat YouTube aw TikTok ltahmilh\n"
        "🖼 Arsel sora ltahsinaha\n"
        "🧠 Aktb ay so2al llhsol ala ijaba\n\n"
        "/clear - mash almohada\n"
        "/stats - ihsa2iyatak",
        reply_markup=main_kb()
    )

async def cmd_clear(u, c):
    history.pop(u.effective_user.id, None)
    await u.message.reply_text("✅ Tm mash tarikh almohada.")

async def cmd_stats(u, c):
    d = load()
    ud = udata(d, u.effective_user.id)
    await u.message.reply_text(
        "📊 Ihsa2iyatak\n\n"
        "📥 Altahmilatat: " + str(ud["dl"]) + "\n"
        "🖼 Alsor: " + str(ud["img"]) + "\n"
        "❓ Alasilat: " + str(ud["q"]) + "\n"
        "👥 Almosta5dmon: " + str(len(d["users"]))
    )

async def on_message(u, c):
    if not u.message or not u.message.text:
        return
    txt = u.message.text.strip()
    uid = u.effective_user.id
    d = load()
    ud = udata(d, uid)
    ud["req"] = ud.get("req", 0) + 1
    d["stats"]["req"] += 1
    save(d)

    if txt == "📥 Video" or txt == "🎵 Audio":
        c.user_data["dl_mode"] = "audio" if "Audio" in txt else "video"
        await u.message.reply_text("🔗 Arsel alrabat:")
        return
    if txt == "🖼 Image":
        await u.message.reply_text("📸 Arsel alsora.")
        return
    if txt == "🧠 AI Question":
        await u.message.reply_text("💬 Aktb so2alak!")
        return
    if txt == "📊 Stats":
        await cmd_stats(u, c)
        return
    if txt == "ℹ️ Help":
        await cmd_help(u, c)
        return

    if re.match(r"https?://[^\s]+", txt):
        c.user_data["url"] = txt
        info = vid_info(txt)
        if info:
            dur = info.get("duration", 0)
            title = str(info.get("title", "Video"))[:50]
            await u.message.reply_text(
                "🎬 " + title + "\n"
                "👤 " + str(info.get("uploader", "-")) + "\n"
                "⏱ " + str(int(dur // 60)) + ":" + str(int(dur % 60)).zfill(2) + "\n\n"
                "Akhtaar alsigha:",
                reply_markup=dl_kb(txt)
            )
        else:
            await u.message.reply_text("❌ Rabat ghayr saleh aw ghayr mad3om.")
        return

    if len(txt) > 1:
        await u.message.chat.send_action(ChatAction.TYPING)
        msg = await u.message.reply_text("🧠 Jaari altafkir...")
        ans = await ask_ai(uid, txt)
        await msg.edit_text(ans)
        d = load()
        ud = udata(d, uid)
        ud["q"] += 1
        d["stats"]["q"] += 1
        save(d)

async def on_photo(u, c):
    if not PIL:
        await u.message.reply_text("❌ Image processing not available.")
        return
    fid = u.message.photo[-1].file_id
    await u.message.reply_text("🖼 Akhtaar alta2thir:", reply_markup=img_kb(fid))

async def on_callback(u, c):
    q = u.callback_query
    await q.answer()
    data = q.data

    if data == "cancel":
        await q.edit_message_text("❌ Tm alilgha.")
        return

    if data.startswith("dv_") or data.startswith("da_"):
        audio = data.startswith("da_")
        url = c.user_data.get("url", "")
        if not url:
            await q.edit_message_text("❌ Anthat aljlsa. A3d irsal alrabat.")
            return
        await q.edit_message_text("⏳ Jaari altahmil...")
        with tempfile.TemporaryDirectory() as tmp:
            loop = asyncio.get_event_loop()
            fp, err = await loop.run_in_executor(None, do_download, url, tmp, audio)
            if err or not fp:
                await q.edit_message_text("❌ " + (err or "Fashal altahmil."))
                return
            if os.path.getsize(fp) > MAX_FILE_MB * 1024 * 1024:
                await q.edit_message_text("❌ Almlf akbar mn " + str(MAX_FILE_MB) + "MB.")
                return
            try:
                await q.edit_message_text("📤 Jaari alraf3...")
                with open(fp, "rb") as f:
                    if audio:
                        await c.bot.send_audio(q.message.chat_id, f, caption="🎵 Tm!")
                    else:
                        await c.bot.send_video(q.message.chat_id, f, caption="🎬 Tm!", supports_streaming=True)
                await q.delete_message()
                d = load()
                d["stats"]["dl"] += 1
                save(d)
            except TelegramError as e:
                await q.edit_message_text("❌ Fashal alraf3: " + str(e)[:100])
        return

    if data.startswith("i_"):
        parts = data.split("_", 2)
        if len(parts) < 3:
            return
        mode = parts[1]
        fid = parts[2]
        label = MODES.get(mode, mode)
        await q.edit_message_text("⏳ " + label + "...")
        try:
            f = await c.bot.get_file(fid)
            bts = bytes(await f.download_as_bytearray())
            result = process_img(bts, mode)
            if not result:
                await q.edit_message_text("❌ Fashal.")
                return
            await q.delete_message()
            await c.bot.send_photo(
                q.message.chat_id,
                photo=io.BytesIO(result),
                caption="✅ " + label,
                reply_markup=img_kb(fid)
            )
            d = load()
            d["stats"]["img"] += 1
            save(d)
        except Exception as e:
            await q.edit_message_text("❌ " + str(e)[:100])

async def on_error(u, c):
    log.error("Error: %s", c.error)
    if isinstance(u, Update) and u.effective_message:
        try:
            await u.effective_message.reply_text("⚠️ Khata, hawal mujadadan.")
        except:
            pass

async def post_init(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Home"),
        BotCommand("help", "Help"),
        BotCommand("clear", "Clear chat"),
        BotCommand("stats", "Statistics"),
    ])

def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN required!")
    print("Bot starting...")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_error_handler(on_error)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
