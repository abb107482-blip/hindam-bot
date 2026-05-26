#!/usr/bin/env python3

# -*- coding: utf-8 -*-

import os, io, re, json, logging, asyncio, tempfile
from datetime import datetime
from pathlib import Path

BOT_TOKEN     = os.environ.get(“BOT_TOKEN”, “”)
ANTHROPIC_KEY = os.environ.get(“ANTHROPIC_KEY”, “”)
ADMIN_IDS     = [int(x) for x in os.environ.get(“ADMIN_IDS”, “0”).split(”,”) if x.strip().isdigit()]
MAX_FILE_MB   = 45

logging.basicConfig(
format=”%(asctime)s | %(levelname)s | %(message)s”,
level=logging.INFO,
handlers=[logging.FileHandler(“bot.log”, encoding=“utf-8”), logging.StreamHandler()]
)
log = logging.getLogger(**name**)

try:
from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup,
ReplyKeyboardMarkup, KeyboardButton, BotCommand)
from telegram.ext import (Application, CommandHandler, MessageHandler,
CallbackQueryHandler, ContextTypes, filters)
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError
except ImportError:
raise SystemExit(“pip install ‘python-telegram-bot[all]’”)

try:
import yt_dlp; YT = True
except ImportError:
YT = False

try:
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ExifTags; PIL = True
except ImportError:
PIL = False

try:
import anthropic; AI = True
except ImportError:
AI = False

DB = Path(“db.json”)

def load():
return json.loads(DB.read_text(“utf-8”)) if DB.exists() else {“users”:{}, “stats”:{“req”:0,“dl”:0,“img”:0,“q”:0}}

def save(d):
DB.write_text(json.dumps(d, ensure_ascii=False, indent=2), “utf-8”)

def udata(d, uid):
k = str(uid)
if k not in d[“users”]:
d[“users”][k] = {“req”:0,“dl”:0,“img”:0,“q”:0,“joined”:datetime.now().isoformat()}
return d[“users”][k]

history: dict = {}

async def ask_ai(uid: int, msg: str) -> str:
if not AI or not ANTHROPIC_KEY:
return fallback(msg)
try:
client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
if uid not in history: history[uid] = []
history[uid].append({“role”:“user”,“content”:msg})
if len(history[uid]) > 20: history[uid] = history[uid][-20:]
r = client.messages.create(
model=“claude-opus-4-5”,
max_tokens=1500,
system=“أنت مساعد بوت تيليغرام ذكي واسمك هيندام. أجب بالعربية بشكل ودود ومنظم مع إيموجي مناسبة. كن مفيداً ومختصراً وشاملاً.”,
messages=history[uid]
)
ans = r.content[0].text
history[uid].append({“role”:“assistant”,“content”:ans})
return ans
except Exception as e:
log.error(f”AI error: {e}”)
return fallback(msg)

def fallback(t: str) -> str:
t = t.lower()
if any(w in t for w in [“مرحبا”,“هاي”,“سلام”,“أهلا”,“هلا”,“hi”,“hello”]):
return “👋 أهلاً! أنا هيندام بوتك الذكي 🤖\nكيف أقدر أساعدك؟”
if any(w in t for w in [“شكرا”,“شكراً”,“ممنون”,“thank”]):
return “😊 العفو! دائماً في خدمتك.”
if any(w in t for w in [“كيف حالك”,“كيفك”]):
return “🤖 بخير! جاهز أساعدك. ماذا تريد؟”
if any(w in t for w in [“من انت”,“اسمك”,“who are you”]):
return “🤖 أنا *هيندام* — بوت ذكي!\n📥 تحميل فيديو\n🖼 تحسين صور\n🧠 إجابة أسئلة\n\n/help للمزيد”
return “🤔 اكتب سؤالك وسأجيبك، أو اكتب /help للمساعدة.”

def valid_url(u): return bool(re.match(r”https?://[^\s]+”, u))

def vid_info(url):
if not YT: return None
try:
with yt_dlp.YoutubeDL({“quiet”:True,“skip_download”:True,“no_warnings”:True}) as y:
return y.extract_info(url, download=False)
except: return None

def do_download(url, out, audio=False):
if not YT: return None, “❌ yt-dlp غير مثبت”
try:
opts = {“quiet”:True,“no_warnings”:True,“outtmpl”:os.path.join(out,”%(title)s.%(ext)s”)}
if audio:
opts[“format”] = “bestaudio/best”
opts[“postprocessors”] = [{“key”:“FFmpegExtractAudio”,“preferredcodec”:“mp3”,“preferredquality”:“192”}]
else:
opts[“format”] = f”best[filesize<{MAX_FILE_MB}M]/best”
opts[“merge_output_format”] = “mp4”
with yt_dlp.YoutubeDL(opts) as y:
y.download([url])
files = list(Path(out).iterdir())
return str(files[0]) if files else None, “”
except yt_dlp.utils.DownloadError as e:
s = str(e)
if “Private” in s: return None, “❌ الفيديو خاص.”
if “age” in s.lower(): return None, “❌ الفيديو مقيّد بالعمر.”
return None, f”❌ خطأ: {s[:150]}”
except Exception as e:
return None, f”❌ خطأ: {str(e)[:150]}”

MODES = {
“enhance”:“✨ تحسين شامل”,“sharpen”:“🔍 تحديد حواف”,“hdr”:“🌈 HDR احترافي”,
“vintage”:“🎞 عتيق”,“grayscale”:“⬛ أبيض وأسود”,“denoise”:“🔵 إزالة ضوضاء”,
“upscale”:“⬆️ رفع الدقة ×2”,“vivid”:“🎨 ألوان زاهية”,
}

def process_img(data: bytes, mode: str):
if not PIL: return None
try:
img = Image.open(io.BytesIO(data))
try:
for tag, val in (img._getexif() or {}).items():
if ExifTags.TAGS.get(tag) == “Orientation”:
img = img.rotate({3:180,6:270,8:90}.get(val,0), expand=True); break
except: pass
if img.mode not in (“RGB”,“L”): img = img.convert(“RGB”)
if mode == “enhance”:
img = ImageEnhance.Brightness(img).enhance(1.1)
img = ImageEnhance.Contrast(img).enhance(1.2)
img = ImageEnhance.Sharpness(img).enhance(2.0)
img = ImageEnhance.Color(img).enhance(1.15)
elif mode == “sharpen”:
img = img.filter(ImageFilter.UnsharpMask(2,150,3))
img = ImageEnhance.Sharpness(img).enhance(3.0)
elif mode == “hdr”:
img = ImageEnhance.Contrast(img).enhance(1.7)
img = ImageEnhance.Color(img).enhance(1.5)
img = ImageEnhance.Brightness(img).enhance(1.05)
elif mode == “vintage”:
img = ImageEnhance.Color(img).enhance(0.5)
img = ImageEnhance.Brightness(img).enhance(0.88)
img = ImageEnhance.Contrast(img).enhance(1.3)
elif mode == “grayscale”:
img = ImageOps.grayscale(img)
img = ImageEnhance.Contrast(img).enhance(1.4)
elif mode == “denoise”:
img = img.filter(ImageFilter.MedianFilter(3))
img = ImageEnhance.Sharpness(img).enhance(1.5)
elif mode == “upscale”:
img = img.resize((img.width*2,img.height*2), Image.LANCZOS)
elif mode == “vivid”:
img = ImageEnhance.Color(img).enhance(1.8)
img = ImageEnhance.Contrast(img).enhance(1.3)
out = io.BytesIO()
fmt = “JPEG” if img.mode == “RGB” else “PNG”
img.save(out, fmt, quality=95, optimize=True)
return out.getvalue()
except Exception as e:
log.error(f”img: {e}”); return None

def img_info(data: bytes) -> str:
if not PIL: return “❌ Pillow غير مثبت”
try:
img = Image.open(io.BytesIO(data))
return (f”📐 الأبعاد: {img.width}×{img.height} بكسل\n”
f”🎨 النمط: {img.mode}\n”
f”📦 الحجم: {len(data)/1024:.1f} KB\n”
f”🖼 الصيغة: {img.format or ‘—’}”)
except: return “❌ تعذّر قراءة الصورة”

def main_kb():
return ReplyKeyboardMarkup([
[KeyboardButton(“📥 تحميل فيديو”), KeyboardButton(“🎵 تحميل صوت”)],
[KeyboardButton(“🖼 تحسين صورة”),  KeyboardButton(“🧠 اسأل الذكاء الاصطناعي”)],
[KeyboardButton(“📊 إحصائياتي”),   KeyboardButton(“ℹ️ مساعدة”)],
], resize_keyboard=True)

def img_kb(fid):
return InlineKeyboardMarkup([
[InlineKeyboardButton(“✨ تحسين شامل”,  callback_data=f”i_enhance_{fid}”),
InlineKeyboardButton(“🌈 HDR”,         callback_data=f”i_hdr_{fid}”)],
[InlineKeyboardButton(“🔍 تحديد حواف”,  callback_data=f”i_sharpen_{fid}”),
InlineKeyboardButton(“🎨 ألوان زاهية”, callback_data=f”i_vivid_{fid}”)],
[InlineKeyboardButton(“🎞 عتيق”,        callback_data=f”i_vintage_{fid}”),
InlineKeyboardButton(“⬛ أبيض وأسود”,  callback_data=f”i_grayscale_{fid}”)],
[InlineKeyboardButton(“🔵 إزالة ضوضاء”, callback_data=f”i_denoise_{fid}”),
InlineKeyboardButton(“⬆️ رفع الدقة”,   callback_data=f”i_upscale_{fid}”)],
[InlineKeyboardButton(“📐 معلومات الصورة”, callback_data=f”i_info_{fid}”)],
[InlineKeyboardButton(“❌ إلغاء”, callback_data=“cancel”)],
])

def dl_kb(url):
k = url[-30:]
return InlineKeyboardMarkup([
[InlineKeyboardButton(“🎬 تحميل فيديو MP4”, callback_data=f”dv_{k}”)],
[InlineKeyboardButton(“🎵 تحميل صوت MP3”,  callback_data=f”da_{k}”)],
[InlineKeyboardButton(“❌ إلغاء”, callback_data=“cancel”)],
])

async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
d = load(); udata(d, u.effective_user.id); save(d)
await u.message.reply_text(
f”🌟 *أهلاً {u.effective_user.first_name}!*\n\n”
“أنا *هيندام* — بوتك الذكي المتكامل 🤖\n\n”
“┌ 📥 تحميل فيديو وصوت\n”
“├ 🖼 تحسين الصور بـ 8 تأثيرات\n”
“├ 🧠 إجابة الأسئلة بالذكاء الاصطناعي\n”
“└ 🔄 ذاكرة محادثة مستمرة\n\n”
“💡 أرسل رابط فيديو، صورة، أو اكتب سؤالك!”,
parse_mode=ParseMode.MARKDOWN, reply_markup=main_kb()
)

async def cmd_help(u: Update, c: ContextTypes.DEFAULT_TYPE):
await u.message.reply_text(
“📖 *دليل الاستخدام*\n\n”
“📥 أرسل رابط يوتيوب أو تيك توك لتحميله\n”
“🖼 أرسل صورة لتحسينها\n”
“🧠 اكتب أي سؤال للحصول على إجابة\n\n”
“🔄 /clear — مسح المحادثة\n”
“📊 /stats — إحصائياتك”,
parse_mode=ParseMode.MARKDOWN, reply_markup=main_kb()
)

async def cmd_clear(u: Update, c: ContextTypes.DEFAULT_TYPE):
history.pop(u.effective_user.id, None)
await u.message.reply_text(“✅ تم مسح تاريخ محادثتك.”)

async def cmd_stats(u: Update, c: ContextTypes.DEFAULT_TYPE):
d = load(); ud = udata(d, u.effective_user.id)
await u.message.reply_text(
f”📊 *إحصائياتك*\n\n”
f”📥 التحميلات: {ud[‘dl’]}\n”
f”🖼 الصور: {ud[‘img’]}\n”
f”❓ الأسئلة: {ud[‘q’]}\n”
f”📅 انضممت: {ud[‘joined’][:10]}\n\n”
f”👥 مجموع المستخدمين: {len(d[‘users’])}”,
parse_mode=ParseMode.MARKDOWN
)

async def cmd_admin(u: Update, c: ContextTypes.DEFAULT_TYPE):
if u.effective_user.id not in ADMIN_IDS:
await u.message.reply_text(“⛔ للمشرفين فقط.”); return
d = load()
await u.message.reply_text(
f”🛡️ *لوحة الإدارة*\n\n”
f”👥 المستخدمون: {len(d[‘users’])}\n”
f”📊 الطلبات: {d[‘stats’][‘req’]}\n”
f”📥 التحميلات: {d[‘stats’][‘dl’]}\n”
f”🖼 الصور: {d[‘stats’][‘img’]}\n”
f”❓ الأسئلة: {d[‘stats’][‘q’]}\n\n”
f”🧠 Claude AI: {‘✅’ if AI else ‘❌’}\n”
f”📥 yt-dlp: {‘✅’ if YT else ‘❌’}\n”
f”🖼 Pillow: {‘✅’ if PIL else ‘❌’}”,
parse_mode=ParseMode.MARKDOWN
)

async def on_message(u: Update, c: ContextTypes.DEFAULT_TYPE):
if not u.message or not u.message.text: return
txt = u.message.text.strip()
uid = u.effective_user.id
d = load(); ud = udata(d, uid); ud[“req”] = ud.get(“req”,0)+1; d[“stats”][“req”] += 1; save(d)

```
if txt in ("📥 تحميل فيديو","🎵 تحميل صوت"):
    c.user_data["dl_mode"] = "audio" if "صوت" in txt else "video"
    await u.message.reply_text("🔗 أرسل الرابط:"); return
if txt == "🖼 تحسين صورة":
    await u.message.reply_text("📸 أرسل الصورة."); return
if txt == "🧠 اسأل الذكاء الاصطناعي":
    await u.message.reply_text("💬 اكتب سؤالك!"); return
if txt == "📊 إحصائياتي":
    await cmd_stats(u, c); return
if txt == "ℹ️ مساعدة":
    await cmd_help(u, c); return

if re.match(r"https?://[^\s]+", txt):
    c.user_data["url"] = txt
    info = vid_info(txt)
    if info:
        dur = info.get("duration",0)
        title = (info.get("title","فيديو") or "فيديو")[:50]
        await u.message.reply_text(
            f"🎬 *{title}*\n"
            f"👤 {info.get('uploader','—')}\n"
            f"⏱ {int(dur//60)}:{int(dur%60):02d}\n"
            f"👁 {info.get('view_count',0):,}\n\n"
            "اختر الصيغة:",
            parse_mode=ParseMode.MARKDOWN, reply_markup=dl_kb(txt)
        )
    else:
        await u.message.reply_text("❌ رابط غير صالح أو غير مدعوم.")
    return

if len(txt) > 1:
    await u.message.chat.send_action(ChatAction.TYPING)
    msg = await u.message.reply_text("🧠 جاري التفكير...")
    ans = await ask_ai(uid, txt)
    await msg.edit_text(ans)
    d = load(); ud = udata(d, uid); ud["q"] += 1; d["stats"]["q"] += 1; save(d)
```

async def on_photo(u: Update, c: ContextTypes.DEFAULT_TYPE):
if not PIL:
await u.message.reply_text(“❌ معالجة الصور غير متاحة.”); return
fid = u.message.photo[-1].file_id
await u.message.reply_text(“🖼 *اختر التأثير:*”, parse_mode=ParseMode.MARKDOWN, reply_markup=img_kb(fid))

async def on_callback(u: Update, c: ContextTypes.DEFAULT_TYPE):
q = u.callback_query
await q.answer()
data = q.data
if data == “cancel”:
await q.edit_message_text(“❌ تم الإلغاء.”); return

```
if data.startswith("dv_") or data.startswith("da_"):
    audio = data.startswith("da_")
    url = c.user_data.get("url","")
    if not url:
        await q.edit_message_text("❌ انتهت الجلسة. أعد إرسال الرابط."); return
    await q.edit_message_text("⏳ جاري التحميل...")
    with tempfile.TemporaryDirectory() as tmp:
        loop = asyncio.get_event_loop()
        fp, err = await loop.run_in_executor(None, do_download, url, tmp, audio)
        if err or not fp:
            await q.edit_message_text(err or "❌ فشل التحميل."); return
        if os.path.getsize(fp) > MAX_FILE_MB*1024*1024:
            await q.edit_message_text(f"❌ الملف أكبر من {MAX_FILE_MB}MB."); return
        try:
            await q.edit_message_text("📤 جاري الرفع...")
            with open(fp,"rb") as f:
                if audio:
                    await c.bot.send_audio(q.message.chat_id, f, caption="🎵 تم!")
                else:
                    await c.bot.send_video(q.message.chat_id, f, caption="🎬 تم!", supports_streaming=True)
            await q.delete_message()
            d = load(); d["stats"]["dl"] += 1; save(d)
        except TelegramError as e:
            await q.edit_message_text(f"❌ فشل الرفع: {str(e)[:100]}")
    return

if data.startswith("i_"):
    parts = data.split("_", 2)
    if len(parts) < 3: return
    _, mode, fid = parts
    if mode == "info":
        await q.edit_message_text("⏳...")
        try:
            f = await c.bot.get_file(fid)
            bts = bytes(await f.download_as_bytearray())
            await q.edit_message_text(f"📐 *معلومات:*\n{img_info(bts)}", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await q.edit_message_text(f"❌ {e}")
        return
    label = MODES.get(mode, mode)
    await q.edit_message_text(f"⏳ {label}...")
    try:
        f = await c.bot.get_file(fid)
        bts = bytes(await f.download_as_bytearray())
        result = process_img(bts, mode)
        if not result:
            await q.edit_message_text("❌ فشل."); return
        await q.delete_message()
        await c.bot.send_photo(
            q.message.chat_id, photo=io.BytesIO(result),
            caption=f"✅ *{label}*", parse_mode=ParseMode.MARKDOWN,
            reply_markup=img_kb(fid)
        )
        d = load(); d["stats"]["img"] += 1; save(d)
    except Exception as e:
        await q.edit_message_text(f"❌ {str(e)[:100]}")
```

async def on_error(u: object, c: ContextTypes.DEFAULT_TYPE):
log.error(f”Error: {c.error}”, exc_info=c.error)
if isinstance(u, Update) and u.effective_message:
try: await u.effective_message.reply_text(“⚠️ خطأ، حاول مجدداً.”)
except: pass

async def post_init(app: Application):
await app.bot.set_my_commands([
BotCommand(“start”,“🏠 البداية”),
BotCommand(“help”,“📖 المساعدة”),
BotCommand(“clear”,“🔄 مسح المحادثة”),
BotCommand(“stats”,“📊 إحصائياتي”),
BotCommand(“admin”,“🛡️ الإدارة”),
])

def main():
if not BOT_TOKEN:
raise SystemExit(“❌ BOT_TOKEN مطلوب!”)
print(“🚀 البوت يعمل…”)
app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
app.add_handler(CommandHandler(“start”, cmd_start))
app.add_handler(CommandHandler(“help”,  cmd_help))
app.add_handler(CommandHandler(“clear”, cmd_clear))
app.add_handler(CommandHandler(“stats”, cmd_stats))
app.add_handler(CommandHandler(“admin”, cmd_admin))
app.add_handler(MessageHandler(filters.PHOTO, on_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
app.add_handler(CallbackQueryHandler(on_callback))
app.add_error_handler(on_error)
app.run_polling(drop_pending_updates=True)

if **name** == “**main**”:
main()
