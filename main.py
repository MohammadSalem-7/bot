import discord
from discord.ext import commands, tasks
import asyncio
import json
import aiohttp
import yt_dlp
import io
from discord import File
import os
from datetime import datetime
import threading
import logging
from discord.ui import Button, Select, View
import random
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests
from io import BytesIO
from dotenv import load_dotenv
# إعداد التسجيل
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# ---------- CONFIG ----------
CONFIG = {
    "TOKEN": os.getenv("TOKEN"),
    "SCAN_INTERVAL_SECONDS": 43200,
    "AUTO_DELETE_UNWHITELISTED": False,
    "NOTIFY_CHANNEL_ID": 1415110690980630528,
    "ADMINS": [1275148740092760170],
    "DATA_FILE": "webhook_guard_data.json",
    "CONFIRM_TIMEOUT_SECONDS": 60,
}

# owner helper
OWNER_ID = CONFIG.get("ADMINS")[0] if CONFIG.get("ADMINS") and len(CONFIG.get("ADMINS"))>0 else None

def is_owner():
    def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)
# -----------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.guild_messages = True
intents.voice_states = True # لازم للـ voice
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, description="Webhook Guard Bot")
# قفل لتأمين الكتابة إلى الملف
file_lock = threading.Lock()
# بيانات ثابتة
def load_data():
    global DATA
    if os.path.exists(CONFIG["DATA_FILE"]):
        try:
            with open(CONFIG["DATA_FILE"], "r", encoding="utf-8") as f:
                DATA = json.load(f)
            if not isinstance(DATA, dict):
                raise ValueError("البيانات في الملف ليست بتنسيق JSON صحيح")
            # التأكد من وجود جميع المفاتيح
            if "whitelisted_webhooks" not in DATA:
                DATA["whitelisted_webhooks"] = []
            if "trusted_creators" not in DATA:
                DATA["trusted_creators"] = []
            if "webhook_log" not in DATA:
                DATA["webhook_log"] = []
            logger.info(f"✅ تم تحميل البيانات من {CONFIG['DATA_FILE']}: {DATA}")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"❌ خطأ في تحميل {CONFIG['DATA_FILE']}: {e}")
            DATA = {
                "whitelisted_webhooks": [],
                "trusted_creators": [],
                "webhook_log": []
            }
            save_data() # إنشاء ملف جديد إذا كان تالفًا
    else:
        DATA = {
            "whitelisted_webhooks": [],
            "trusted_creators": [],
            "webhook_log": []
        }
        save_data() # إنشاء ملف جديد
    return DATA
def save_data():
    with file_lock:
        try:
            with open(CONFIG["DATA_FILE"], "w", encoding="utf-8") as f:
                json.dump(DATA, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ تم حفظ البيانات في {CONFIG['DATA_FILE']}")
        except Exception as e:
            logger.error(f"❌ خطأ في حفظ {CONFIG['DATA_FILE']}: {e}")
# تحميل البيانات عند بدء التشغيل
DATA = load_data()
# قائمة الأعضاء المسموح لهم بإرسال لينكات و GIFs في الرومات المفتوحة (لكل سيرفر)
ALLOWED_LINK_USERS = {}  # {guild_id: set of user_ids}
def load_allowed_users():
    if os.path.exists("allowed_links_users.json"):
        try:
            with open("allowed_links_users.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                # تحويل من صيغة قديمة إذا لزم (لتوافق مع النسخة القديمة)
                if isinstance(data, list):
                    return {}
                return {int(k): set(v) for k, v in data.items()}
        except:
            return {}
    return {}
def save_allowed_users():
    with open("allowed_links_users.json", "w", encoding="utf-8") as f:
        json.dump({k: list(v) for k, v in ALLOWED_LINK_USERS.items()}, f, ensure_ascii=False)
ALLOWED_LINK_USERS = load_allowed_users() # تحميل القائمة عند التشغيل

# قائمة المسموحين لأوامر DM الجديدة (لكل سيرفر)
DM_ALLOWED_USERS = {}  # {guild_id: set of user_ids}
def load_dm_allowed_users():
    if os.path.exists("dm_allowed.json"):
        try:
            with open("dm_allowed.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                # تحويل من صيغة قديمة إذا لزم
                if isinstance(data, list):
                    return {}
                return {int(k): set(v) for k, v in data.items()}
        except:
            return {}
    return {}
def save_dm_allowed_users():
    with open("dm_allowed.json", "w", encoding="utf-8") as f:
        json.dump({k: list(v) for k, v in DM_ALLOWED_USERS.items()}, f, ensure_ascii=False)
DM_ALLOWED_USERS = load_dm_allowed_users()
# قائمة المسموحين لأمر مسي_عليهم (لكل سيرفر)
MESI_ALLOWED_USERS = {}  # {guild_id: set of user_ids}
def load_mesi_allowed_users():
    if os.path.exists("mesi_allowed.json"):
        try:
            with open("mesi_allowed.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                # تحويل من صيغة قديمة إذا لزم
                if isinstance(data, list):
                    return {}
                return {int(k): set(v) for k, v in data.items()}
        except:
            return {}
    return {}
def save_mesi_allowed_users():
    with open("mesi_allowed.json", "w", encoding="utf-8") as f:
        json.dump({k: list(v) for k, v in MESI_ALLOWED_USERS.items()}, f, ensure_ascii=False)
MESI_ALLOWED_USERS = load_mesi_allowed_users()  # تحميل القائمة عند التشغيل
# قائمة اليوزرز الممنوعين من استخدام البوت كليًا
BLACKLISTED_USERS = set()

def load_blacklisted_users():
    if os.path.exists("blacklisted_users.json"):
        try:
            with open("blacklisted_users.json", "r", encoding="utf-8") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_blacklisted_users():
    with open("blacklisted_users.json", "w", encoding="utf-8") as f:
        json.dump(list(BLACKLISTED_USERS), f, ensure_ascii=False)

BLACKLISTED_USERS = load_blacklisted_users()  # تحميل القائمة عند التشغيل
# دالة التحقق من الأدمن (الأونر)
def is_admin():
    def predicate(ctx):
        return ctx.author.id in CONFIG["ADMINS"]
    return commands.check(predicate)
# قائمة المسموح لهم بإضافة بوتات للسيرفر (لكل سيرفر)
BOT_ALLOWED_USERS = {}  # {guild_id: set of user_ids}

def load_bot_allowed_users():
    if os.path.exists("bot_allowed_users.json"):
        try:
            with open("bot_allowed_users.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                # تحويل من صيغة قديمة إذا لزم
                if isinstance(data, list):
                    return {}
                return {int(k): set(v) for k, v in data.items()}
        except:
            return {}
    return {}

def save_bot_allowed_users():
    with open("bot_allowed_users.json", "w", encoding="utf-8") as f:
        json.dump({k: list(v) for k, v in BOT_ALLOWED_USERS.items()}, f, ensure_ascii=False)

BOT_ALLOWED_USERS = load_bot_allowed_users()  # تحميل القائمة عند التشغيل

# دالة التحقق من السماح لـ DM (أونر أو مسموح في السيرفر الحالي)
def is_dm_allowed():
    def predicate(ctx):
        if ctx.author.id in CONFIG["ADMINS"]:
            return True
        guild_id = ctx.guild.id if ctx.guild else None
        if guild_id and guild_id in DM_ALLOWED_USERS:
            return ctx.author.id in DM_ALLOWED_USERS[guild_id]
        return False
    return commands.check(predicate)
# دالة التحقق من السماح لأمر مسي_عليهم (أونر أو مسموح في السيرفر الحالي)
def is_mesi_allowed():
    def predicate(ctx):
        if ctx.author.id == 1275148740092760170:  # اليوزر المحدد
            return True
        guild_id = ctx.guild.id if ctx.guild else None
        if guild_id and guild_id in MESI_ALLOWED_USERS:
            return ctx.author.id in MESI_ALLOWED_USERS[guild_id]
        return False
    return commands.check(predicate)
# دالة التحقق من أن اليوزر مش في البلاك ليست
def is_not_blacklisted():
    def predicate(ctx):
        if ctx.author.id in CONFIG["ADMINS"]:
            return True  # الأدمن يقدر يستخدم كل حاجة حتى لو في البلاك ليست (اختياري)
        return ctx.author.id not in BLACKLISTED_USERS
    return commands.check(predicate)
# دالة لتسجيل إجراء في السجل
def log_webhook_action(action: str, webhook_id: str, user_id: int, guild_id: int):
    log_entry = {
        "action": action,
        "webhook_id": webhook_id,
        "user_id": user_id,
        "guild_id": guild_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    DATA["webhook_log"].append(log_entry)
    save_data()
# دالة لإنشاء Embed احترافي
def create_embed(title: str, description: str, color: discord.Color = discord.Color.blue()):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="♠ Mohammed Salem ♠ | Webhook Guard")
    from datetime import datetime, timezone
    embed.timestamp = datetime.now(timezone.utc)
    return embed
# دالة إرسال تقرير بـ Embed
async def send_report(guild: discord.Guild, title: str, description: str, color: discord.Color = discord.Color.blue()):
    embed = create_embed(title, description, color)
    embed.add_field(name="Server", value=f"{guild.name} ({guild.id})", inline=False)
    if CONFIG["NOTIFY_CHANNEL_ID"]:
        ch = bot.get_channel(CONFIG["NOTIFY_CHANNEL_ID"])
        if ch:
            await ch.send(embed=embed)
    owner = guild.owner
    if owner:
        try:
            await owner.send(embed=embed)
        except Exception as e:
            logger.error(f"❌ فشل إرسال رسالة للمالك {owner}: {e}")
    for admin_id in CONFIG["ADMINS"]:
        try:
            admin = await bot.fetch_user(admin_id)
            if admin:
                await admin.send(embed=embed)
        except Exception as e:
            logger.error(f"❌ فشل إرسال رسالة للأدمن {admin_id}: {e}")
# مراقبة إنشاء/حذف/تعديل الويبهوكات
@bot.event
async def on_guild_webhook_update(channel, webhook):
    try:
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
            if entry.target.id == webhook.id:
                log_webhook_action("create", str(webhook.id), entry.user.id, channel.guild.id)
                await send_report(channel.guild, "Webhook Created", f"Webhook `{webhook.name or 'غير معروف'}` ({webhook.id}) created by <@{entry.user.id}> in channel <#{channel.id}>", discord.Color.green())
                break
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_delete):
            if entry.target.id == webhook.id:
                log_webhook_action("delete", str(webhook.id), entry.user.id, channel.guild.id)
                await send_report(channel.guild, "Webhook Deleted", f"Webhook `{webhook.name or 'غير معروف'}` ({webhook.id}) deleted by <@{entry.user.id}>", discord.Color.red())
                break
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_update):
            if entry.target.id == webhook.id:
                log_webhook_action("edit", str(webhook.id), entry.user.id, channel.guild.id)
                await send_report(channel.guild, "Webhook Edited", f"Webhook `{webhook.name or 'غير معروف'}` ({webhook.id}) edited by <@{entry.user.id}>", discord.Color.orange())
                break
    except Exception as e:
        logger.error(f"❌ خطأ في حدث تحديث الويبهوك: {e}")
@bot.event
async def on_ready():
    logger.info(f"تم تسجيل الدخول كـ: {bot.user} (id: {bot.user.id})")
    logger.info("بدء مهمة الفحص الدوري...")
    periodic_scan.start()
# فحص السيرفر
async def scan_guild_for_webhooks(guild: discord.Guild, auto_delete: bool | None = None):
    if auto_delete is None:
        auto_delete = CONFIG["AUTO_DELETE_UNWHITELISTED"]
    results = []
    try:
        webhooks = await guild.webhooks()
    except discord.Forbidden:
        return {"guild": guild, "error": "ممنوع (البوت لا يملك صلاحية مشاهدة الويبهوكس)"}
    except Exception as e:
        return {"guild": guild, "error": str(e)}
    for wh in webhooks:
        wh_info = {
            "id": wh.id,
            "name": wh.name or "غير معروف",
            "channel_id": wh.channel.id if wh.channel else None,
            "url": "Webhook مخفي",
            "owner_id": getattr(wh, "user", None).id if getattr(wh, "user", None) else None,
            "created_at": None,
            "status": "whitelisted" if str(wh.id) in DATA["whitelisted_webhooks"] or (wh.user and wh.user.id in DATA["trusted_creators"]) else "unwhitelisted"
        }
        creator_id = None
        try:
            async for entry in guild.audit_logs(limit=50, action=discord.AuditLogAction.webhook_create):
                if getattr(entry.target, "id", None) == wh.id:
                    creator_id = entry.user.id
                    wh_info["created_at"] = entry.created_at.isoformat()
                    break
        except discord.Forbidden:
            wh_info["note"] = "لا صلاحية للوصول إلى سجلات التدقيق"
        except Exception:
            pass
        wh_info["creator_id"] = creator_id
        if wh_info["status"] == "unwhitelisted" and auto_delete:
            try:
                await wh.delete(reason="إزالة تلقائية: غير مسموح")
                wh_info["action"] = "deleted"
                log_webhook_action("delete", str(wh.id), bot.user.id, guild.id)
            except discord.Forbidden:
                wh_info["action"] = "failed_delete_forbidden"
            except Exception as e:
                wh_info["action"] = f"failed_delete:{e}"
        results.append(wh_info)
    return {"guild": guild, "results": results}
@tasks.loop(seconds=CONFIG["SCAN_INTERVAL_SECONDS"])
async def periodic_scan():
    logger.info(f"[{datetime.utcnow().isoformat()}] بدء الفحص الدوري...")
    for guild in bot.guilds:
        info = await scan_guild_for_webhooks(guild)
        if "error" in info:
            await send_report(guild, "خطأ الفحص", info["error"], discord.Color.red())
            continue
        lines = []
        for r in info["results"]:
            s = f"Webhook `{r['name']}` ({r['id']}) في القناة <#{r['channel_id']}> → {r['status']}"
            if r.get("action"):
                s += f" | الإجراء: {r['action']}"
            if r.get("creator_id"):
                s += f" | المنشئ: <@{r['creator_id']}>"
            lines.append(s)
        if lines:
            await send_report(guild, "نتائج الفحص الدوري", "\n".join(lines))
# أمر لعرض سجل الويبهوكات من Audit Logs مباشرة
@bot.command(name="medoweblog")
@is_admin()
async def medoweblog(ctx, webhook_id: str = None):
    """عرض سجل إجراءات الويبهوكات من Audit Logs (اختياري: لويبهوك معين)"""
    embed = create_embed("📜 سجل الويبهوكات", "جاري استرجاع السجلات من Audit Logs...")
    await ctx.send(embed=embed)
    actions = [
        discord.AuditLogAction.webhook_create,
        discord.AuditLogAction.webhook_delete,
        discord.AuditLogAction.webhook_update
    ]
    logs = []
    try:
        async for entry in ctx.guild.audit_logs(limit=50):
            if entry.action in actions:
                if webhook_id is None or str(entry.target.id) == webhook_id:
                    action_str = {
                        discord.AuditLogAction.webhook_create: "إنشاء",
                        discord.AuditLogAction.webhook_delete: "حذف",
                        discord.AuditLogAction.webhook_update: "تعديل"
                    }[entry.action]
                    name = getattr(entry.target, "name", "غير معروف")
                    log_entry = f"إجراء: {action_str}\nWebhook: {name} ({entry.target.id})\nبواسطة: <@{entry.user.id}>\nالتوقيت: {entry.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
                    logs.append(log_entry)
    except discord.Forbidden:
        embed = create_embed("❌ خطأ", "البوت لا يملك صلاحية الوصول إلى Audit Logs.", discord.Color.red())
        await ctx.send(embed=embed)
        return
    except Exception as e:
        embed = create_embed("❌ خطأ", f"حدث خطأ: {str(e)}", discord.Color.red())
        await ctx.send(embed=embed)
        return
    if not logs:
        embed = create_embed("📭 السجل", "لا توجد سجلات متاحة.", discord.Color.red())
        await ctx.send(embed=embed)
        return
    embed = create_embed("📜 سجل الويبهوكات من Audit Logs", "آخر السجلات:")
    for i, log in enumerate(logs[:10], 1):
        embed.add_field(name=f"سجل #{i}", value=log, inline=False)
    await ctx.send(embed=embed)
# كلاس لـ View التفاعلي
class WebhookManageView(View):
    def __init__(self, webhook_id: str, guild: discord.Guild):
        super().__init__(timeout=60)
        self.webhook_id = webhook_id
        self.guild = guild
    @discord.ui.button(label="Add to Whitelist", style=discord.ButtonStyle.green)
    async def whitelist_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in CONFIG["ADMINS"]:
            await interaction.response.send_message("❌ ممنوع! الأمر للأدمنز فقط.", ephemeral=True)
            return
        await interaction.response.defer()
        DATA["whitelisted_webhooks"].append(self.webhook_id)
        save_data()
        log_webhook_action("whitelist", self.webhook_id, interaction.user.id, self.guild.id)
        embed = create_embed("✅ تم", f"Webhook {self.webhook_id} أُضيف إلى قائمة السماح.", discord.Color.green())
        await interaction.followup.send(embed=embed)
        self.stop()
    @discord.ui.button(label="Delete Webhook", style=discord.ButtonStyle.red)
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in CONFIG["ADMINS"]:
            await interaction.response.send_message("❌ ممنوع! الأمر للأدمنز فقط.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            webhooks = await self.guild.webhooks()
            webhook = next((w for w in webhooks if str(w.id) == self.webhook_id), None)
            if webhook:
                await webhook.delete(reason="إزالة بواسطة الأمر medoscan")
                log_webhook_action("delete", self.webhook_id, interaction.user.id, self.guild.id)
                embed = create_embed("🗑️ تم", f"Webhook {self.webhook_id} تم حذفه.", discord.Color.green())
            else:
                embed = create_embed("❌ خطأ", "لم يتم العثور على الويبهوك.", discord.Color.red())
        except discord.Forbidden:
            embed = create_embed("❌ خطأ", "البوت لا يملك صلاحية الحذف.", discord.Color.red())
        except Exception as e:
            embed = create_embed("❌ خطأ", f"حدث خطأ: {str(e)}", discord.Color.red())
        await interaction.followup.send(embed=embed)
        self.stop()
# أمر تفاعلي لفحص السيرفر
@bot.command(name="medoscan")
@is_admin()
async def medoscan(ctx):
    """فحص تفاعلي باستخدام قائمة منسدلة"""
    embed = create_embed("🔍 جارٍ الفحص", "جاري تحميل الويبهوكات...")
    await ctx.send(embed=embed)
    info = await scan_guild_for_webhooks(ctx.guild, auto_delete=False)
    if "error" in info:
        embed = create_embed("❌ خطأ", info["error"], discord.Color.red())
        await ctx.send(embed=embed)
        return
    if not info["results"]:
        embed = create_embed("✅ الفحص", "مفيش أي ويبهوكس.", discord.Color.green())
        await ctx.send(embed=embed)
        return
    options = [
        discord.SelectOption(label=f"{r['name']} ({r['id']})", value=str(r['id']), description=f"Status: {r['status']}")
        for r in info["results"]
    ]
    class ScanSelect(Select):
        def __init__(self, options, info, guild):
            super().__init__(placeholder="اختر ويبهوك", options=options)
            self.info = info
            self.guild = guild
        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id not in CONFIG["ADMINS"]:
                await interaction.response.send_message("❌ ممنوع! الأمر للأدمنز فقط.", ephemeral=True)
                return
            await interaction.response.defer()
            webhook_id = self.values[0]
            selected = next((r for r in self.info["results"] if str(r["id"]) == webhook_id), None)
            if not selected:
                embed = create_embed("❌ خطأ", "لم يتم العثور على الويبهوك.", discord.Color.red())
                await interaction.followup.send(embed=embed)
                return
            embed = create_embed(
                "تفاصيل الويبهوك",
                f"الاسم: {selected['name']}\nالمعرف: {selected['id']}\nالقناة: <#{selected['channel_id']}>\nالحالة: {selected['status']}\nالمنشئ: <@{selected['creator_id']}> إذا متوفر",
                discord.Color.blue()
            )
            view = WebhookManageView(webhook_id, self.guild)
            await interaction.followup.send(embed=embed, view=view)
    view = View(timeout=60)
    view.add_item(ScanSelect(options, info, ctx.guild))
    embed = create_embed("فحص الويبهوكات", "اختر ويبهوك من القائمة لإدارته:")
    await ctx.send(embed=embed, view=view)
# ====================== أوامر الـ Voice الجديدة ======================
@bot.command(name="join")
@is_not_blacklisted()
@is_owner()
async def join(ctx):
    """البوت يدخل الروم الصوتي اللي أنت فيه"""
    if ctx.author.voice and ctx.author.voice.channel:
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
            await ctx.send(f"🔊 نقلت للروم: **{channel.name}**")
        else:
            await channel.connect()
            await ctx.send(f"🔊 دخلت الروم: **{channel.name}**")
    else:
        await ctx.send("❌ لازم تكون في روم صوتي الأول!")

@bot.command(name="joinvc")
@is_not_blacklisted()
@is_owner()
async def join_specific(ctx, channel_id: int):
    """البوت يدخل روم صوتي بالـ ID"""
    channel = bot.get_channel(channel_id)
   
    if channel is None:
        await ctx.send("❌ مش لاقي الروم ده! تأكد من الـ ID.")
        return
   
    if not isinstance(channel, discord.VoiceChannel):
        await ctx.send("❌ الـ ID ده مش لـ voice channel!")
        return
   
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
        await ctx.send(f"🔊 نقلت للروم: **{channel.name}**")
    else:
        await channel.connect()
        await ctx.send(f"🔊 دخلت الروم: **{channel.name}**")

@bot.command(name="leave")
@is_not_blacklisted()
@is_owner()
async def leave(ctx):
    """البوت يخرج من الروم الصوتي"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("🔇 خرجت من الروم الصوتي!")
    else:
        await ctx.send("❌ أنا مش في أي روم صوتي أصلاً!")

#======================================================================
from discord import FFmpegPCMAudio, PCMVolumeTransformer

# ====================== نظام الأغاني المحلية - النسخة الفخمة v2 ======================

try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC
    from io import BytesIO
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("تحذير: mutagen غير مثبت → لن نعرض مدة الأغنية أو صورة الألبوم")

MUSIC_FOLDER = "mu"

# التأكد من وجود الفولدر
if not os.path.exists(MUSIC_FOLDER):
    os.makedirs(MUSIC_FOLDER)
    print(f"تم إنشاء فولدر {MUSIC_FOLDER} – ضيف فيه ملفات .mp3")

# حالة كل سيرفر
class GuildMusic:
    def __init__(self):
        self.queue = []               # قائمة أسماء الملفات المنتظرة
        self.current = None           # اسم الملف الحالي
        self.vc = None                # voice client
        self.message = None           # رسالة Now Playing
        self.is_paused = False
        self.volume = 1.0             # 1.0 = 100%

music_guilds = {}  # {guild_id: GuildMusic}

def get_music_files():
    """جلب كل ملفات mp3 من الفولدر"""
    return [f for f in os.listdir(MUSIC_FOLDER) if f.lower().endswith('.mp3')]

def get_song_duration(file_path):
    """إرجاع مدة الأغنية بالصيغة mm:ss"""
    if not MUTAGEN_AVAILABLE:
        return "غير متاح"
    try:
        audio = MP3(file_path)
        duration_sec = int(audio.info.length)
        minutes = duration_sec // 60
        seconds = duration_sec % 60
        return f"{minutes}:{seconds:02d}"
    except:
        return "غير معروف"

def get_album_art(file_path):
    """استخراج صورة الألبوم إذا وُجدت"""
    if not MUTAGEN_AVAILABLE:
        return None
    try:
        tags = ID3(file_path)
        for tag in tags.getall("APIC"):
            if tag.type == 3:  # Cover (front)
                return BytesIO(tag.data)
        return None
    except:
        return None

# ─── واجهة التحكم الفخمة ────────────────────────────────────────────────
class MusicControls(View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    async def get_state(self):
        return music_guilds.get(self.guild_id)

    async def update_np(self, state):
        if not state or not state.message or not state.current:
            return
        try:
            file_path = os.path.join(MUSIC_FOLDER, state.current)
            duration = get_song_duration(file_path)
            art_buffer = get_album_art(file_path)

            embed = discord.Embed(
                title="🎵 دلوقتي بشغل",
                description=f"**{state.current}**",
                color=discord.Color.purple()
            )
            embed.add_field(name="المدة", value=duration, inline=True)
            embed.add_field(name="الصوت", value=f"{int(state.volume * 100)}%", inline=True)
            embed.add_field(name="في الانتظار", value=len(state.queue), inline=True)
            embed.add_field(name="الحالة", value="⏸️ متوقف مؤقتًا" if state.is_paused else "▶️ شغال", inline=True)

            files = []
            if art_buffer:
                embed.set_thumbnail(url="attachment://cover.jpg")
                files = [discord.File(art_buffer, filename="cover.jpg")]

            await state.message.edit(embed=embed, files=files, view=self)
        except Exception as e:
            print(f"خطأ في تحديث Now Playing: {e}")

    @discord.ui.button(label="Pause / Resume", style=discord.ButtonStyle.secondary, emoji="⏯️")
    async def pause_resume(self, interaction: discord.Interaction, button: Button):
        state = await self.get_state()
        if not state or not state.vc:
            return await interaction.response.send_message("مفيش تشغيل حاليًا!", ephemeral=True)

        if state.vc.is_paused():
            state.vc.resume()
            state.is_paused = False
            msg = "▶️ رجّع التشغيل!"
        else:
            state.vc.pause()
            state.is_paused = True
            msg = "⏸️ وقّفت مؤقتًا!"

        await interaction.response.send_message(msg, ephemeral=True)
        await self.update_np(state)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary, emoji="⏭️")
    async def skip(self, interaction: discord.Interaction, button: Button):
        state = await self.get_state()
        if not state or not state.vc:
            return await interaction.response.send_message("مفيش تشغيل!", ephemeral=True)

        if state.vc.is_playing() or state.vc.is_paused():
            state.vc.stop()
            await interaction.response.send_message("⏭️ تم التخطي!", ephemeral=True)

    @discord.ui.button(label="Replay", style=discord.ButtonStyle.blurple, emoji="🔁")
    async def replay(self, interaction: discord.Interaction, button: Button):
        state = await self.get_state()
        if not state or not state.current:
            return await interaction.response.send_message("مفيش أغنية حالية!", ephemeral=True)

        # إعادة إدراج الأغنية في بداية الانتظار
        state.queue.insert(0, state.current)
        if state.vc.is_playing() or state.vc.is_paused():
            state.vc.stop()
        await interaction.response.send_message(f"🔁 هيعاد تشغيل: **{state.current}**", ephemeral=True)

    @discord.ui.button(label="Stop & Leave", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_leave(self, interaction: discord.Interaction, button: Button):
        state = await self.get_state()
        if not state or not state.vc:
            return await interaction.response.send_message("مفيش تشغيل!", ephemeral=True)

        state.vc.stop()
        await state.vc.disconnect()
        music_guilds.pop(self.guild_id, None)

        if state.message:
            try:
                await state.message.edit(content="🛑 تم إيقاف التشغيل والخروج من الروم", embed=None, view=None, attachments=[])
            except:
                pass

        await interaction.response.send_message("⏹️ وقفت كل حاجة وخرجت من الروم!", ephemeral=True)

    @discord.ui.select(
        placeholder="تغيير مستوى الصوت",
        options=[
            discord.SelectOption(label="50%", value="0.5"),
            discord.SelectOption(label="75%", value="0.75"),
            discord.SelectOption(label="100%", value="1.0", default=True),
            discord.SelectOption(label="125%", value="1.25"),
            discord.SelectOption(label="150%", value="1.5"),
        ]
    )
    async def volume_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        state = await self.get_state()
        if not state or not state.vc:
            return await interaction.response.send_message("مفيش تشغيل حاليًا!", ephemeral=True)

        vol = float(select.values[0])
        state.volume = vol

        # تغيير الصوت فورًا إذا كان فيه مصدر شغال
        if state.vc.source:
            state.vc.source.volume = vol

        await interaction.response.send_message(f"🔊 تم تغيير الصوت إلى **{int(vol*100)}%**", ephemeral=True)
        await self.update_np(state)

# ─── أمر !play (مع دعم الـ queue والصورة والمدة + حل مشكلة طول الاسم) ───────
@bot.command(name="play")
@is_not_blacklisted()
@is_owner()
async def play_local(ctx):
    """تشغيل أغنية من فولدر mu مع واجهة تحكم فخمة (محسّنة)"""
    if not ctx.author.voice:
        return await ctx.send("لازم تكون في روم صوتي!")

    channel = ctx.author.voice.channel

    if ctx.guild.id not in music_guilds:
        music_guilds[ctx.guild.id] = GuildMusic()

    state = music_guilds[ctx.guild.id]

    # ── التعامل مع الاتصال القديم بشكل آمن ──
    try:
        if state.vc:
            if state.vc.is_connected():
                if state.vc.channel != channel:
                    await state.vc.move_to(channel)
            else:
                await state.vc.disconnect()
                state.vc = await channel.connect()
        else:
            state.vc = await channel.connect()
    except discord.ClientException as e:
        # Already connected
        if "already connected" in str(e).lower():
            await ctx.send("البوت متصل بالفعل بروم صوتي، هحاول اعمل إعادة اتصال آمنة...")
            try:
                await state.vc.disconnect()
                state.vc = await channel.connect()
            except Exception as e2:
                return await ctx.send(f"فشل إعادة الاتصال: {e2}")
        else:
            return await ctx.send(f"خطأ أثناء الاتصال بالروم: {e}")

    songs = get_music_files()
    if not songs:
        return await ctx.send("الفولدر `mu` فاضي! ضيف ملفات .mp3 وحاول تاني.")

    # ── إعداد قائمة الأغاني للاختيار ──
    options = []
    for idx, song in enumerate(songs[:25]):
        label = song if len(song) <= 97 else song[:94] + "..."
        value = str(idx)
        options.append(discord.SelectOption(label=label, value=value, description=f"رقم {idx+1}"))

    class SongSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(
                placeholder="اختر الأغنية...",
                options=options,
                min_values=1,
                max_values=1
            )

        async def callback(self, interaction: discord.Interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("القائمة دي للي طلب الأمر بس!", ephemeral=True)

            selected_idx = int(self.values[0])
            selected_song = songs[selected_idx]

            state.queue.append(selected_song)

            if not state.current and not state.vc.is_playing() and not state.vc.is_paused():
                await self.start_playing(interaction)
            else:
                await interaction.response.send_message(f"➕ تمت إضافة **{selected_song}** للانتظار", ephemeral=True)

        async def start_playing(self, interaction=None):
            if not state.queue:
                state.current = None
                if state.message:
                    try:
                        await state.message.edit(content="القائمة خلّصت!", embed=None, view=None, attachments=[])
                    except:
                        pass
                return

            state.current = state.queue.pop(0)
            file_path = os.path.join(MUSIC_FOLDER, state.current)

            try:
                raw_source = discord.FFmpegPCMAudio(file_path, options="-vn")
                source = discord.PCMVolumeTransformer(raw_source, volume=state.volume)

                state.vc.play(
                    source,
                    after=lambda e: bot.loop.create_task(self.after_playing(e))
                )

                duration = get_song_duration(file_path)
                art_buffer = get_album_art(file_path)

                embed = discord.Embed(
                    title="🎵 دلوقتي بشغل",
                    description=f"**{state.current}**",
                    color=discord.Color.purple()
                )
                embed.add_field(name="المدة", value=duration, inline=True)
                embed.add_field(name="الصوت", value=f"{int(state.volume * 100)}%", inline=True)
                embed.add_field(name="في الانتظار", value=len(state.queue), inline=True)
                embed.add_field(name="الحالة", value="▶️ شغال", inline=True)

                files = []
                if art_buffer:
                    embed.set_thumbnail(url="attachment://cover.jpg")
                    files = [discord.File(art_buffer, filename="cover.jpg")]

                if state.message:
                    await state.message.edit(embed=embed, files=files, view=MusicControls(ctx.guild.id))
                else:
                    state.message = await ctx.send(embed=embed, files=files, view=MusicControls(ctx.guild.id))

                if interaction and not interaction.response.is_done():
                    await interaction.edit_original_response(
                        content=f"▶️ بدأ تشغيل: **{state.current}**",
                        embed=embed,
                        view=None,
                        files=files
                    )

            except Exception as e:
                error_msg = f"خطأ أثناء تشغيل {state.current}: {str(e)}"
                print(error_msg)
                if interaction:
                    await interaction.edit_original_response(content=error_msg, view=None)
                state.current = None
                await self.start_playing()

        async def after_playing(self, error):
            if error:
                print(f"خطأ بعد التشغيل: {error}")
            state.current = None
            await self.start_playing()

    view = discord.ui.View(timeout=120)
    view.add_item(SongSelect())

    embed = discord.Embed(
        title="🎶 اختار أغنية من المجلد",
        description=f"الأغاني المتاحة في `{MUSIC_FOLDER}` ({len(songs)}):",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=view)

# ─── أوامر إضافية ────────────────────────────────────────────────────
@bot.command(name="skip")
@is_not_blacklisted()
@is_owner()
async def skip_song(ctx):
    """تخطي الأغنية الحالية مع حماية من أي اتصال صوتي قديم"""
    state = music_guilds.get(ctx.guild.id)
    if not state or not state.vc:
        return await ctx.send("مفيش تشغيل حاليًا!")

    try:
        if state.vc.is_playing() or state.vc.is_paused():
            state.vc.stop()
            await ctx.send("⏭️ تم تخطي الأغنية!")
        else:
            await ctx.send("مفيش أغنية شغالة عشان أتخطاها!")
    except Exception as e:
        print(f"خطأ أثناء تخطي الأغنية: {e}")
        await ctx.send(f"❌ حصل خطأ أثناء التخطي: {e}")


@bot.command(name="stop")
@is_not_blacklisted()
@is_owner()
async def stop_music(ctx):
    """إيقاف التشغيل والخروج من الروم مع فصل أي اتصال قديم"""
    state = music_guilds.get(ctx.guild.id)
    if not state:
        return await ctx.send("مفيش تشغيل أصلاً!")

    # وقف التشغيل الحالي ومسح قائمة الانتظار
    if state.vc:
        try:
            if state.vc.is_playing() or state.vc.is_paused():
                state.vc.stop()
        except Exception as e:
            print(f"خطأ أثناء إيقاف الأغنية: {e}")

        try:
            if state.vc.is_connected():
                await state.vc.disconnect()
        except Exception as e:
            print(f"خطأ أثناء قطع الاتصال بالروم: {e}")

    state.queue.clear()
    state.current = None
    music_guilds.pop(ctx.guild.id, None)

    if state.message:
        try:
            await state.message.edit(content="🛑 تم إيقاف التشغيل والخروج من الروم", embed=None, view=None, attachments=[])
        except:
            pass

    await ctx.send("⏹️ تم إيقاف كل شيء وفصل البوت من الروم!")

@bot.command(name="songs")
@is_not_blacklisted()
@is_owner()
async def list_songs(ctx):
    """عرض قائمة الأغاني المتاحة في الفولدر"""
    songs = get_music_files()
    if not songs:
        return await ctx.send("الفولدر `mu` فاضي حاليًا!")

    embed = discord.Embed(
        title=f"📂 الأغاني المتاحة ({len(songs)})",
        description="\n".join([f"• {i+1}. {song}" for i, song in enumerate(songs)]),
        color=discord.Color.blue()
    )
    embed.set_footer(text="اكتب !play عشان تختار وتشغل")
    await ctx.send(embed=embed)

# ==================================================================
# باقي الأوامر
@bot.command(name="medoscan_now")
@is_admin()
async def medoscan_now(ctx):
    """فحص سريع للسيرفر كله"""
    embed = create_embed("🔍 جارٍ الفحص", "جاري فحص الويبهوكات...")
    await ctx.send(embed=embed)
    info = await scan_guild_for_webhooks(ctx.guild)
    if "error" in info:
        embed = create_embed("❌ خطأ", info["error"], discord.Color.red())
        await ctx.send(embed=embed)
        return
    if not info["results"]:
        embed = create_embed("✅ الفحص", "مفيش أي ويبهوكس.", discord.Color.green())
        await ctx.send(embed=embed)
        return
    embed = create_embed("نتائج الفحص", "تفاصيل الويبهوكات في السيرفر:")
    for r in info["results"]:
        action = r.get("action", "لا إجراء")
        creator = f"<@{r['creator_id']}>" if r.get("creator_id") else "غير معروف"
        embed.add_field(
            name=f"Webhook: {r['name']} ({r['id']})",
            value=f"القناة: <#{r['channel_id']}>\nالحالة: {r['status']}\nالإجراء: {action}\nالمنشئ: {creator}",
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name="medoscan_channel")
@is_admin()
async def medoscan_channel(ctx, channel_id: int):
    """فحص ويبهوكس قناة معينة"""
    channel = ctx.guild.get_channel(channel_id)
    if not channel:
        embed = create_embed("❌ خطأ", "القناة مش موجودة أو المعرف غلط.", discord.Color.red())
        await ctx.send(embed=embed)
        return
    try:
        webhooks = await channel.webhooks()
    except discord.Forbidden:
        embed = create_embed("⚠️ خطأ", "البوت مش معاه صلاحيات يشوف ويبهوكس القناة دي.", discord.Color.red())
        await ctx.send(embed=embed)
        return
    except Exception as e:
        embed = create_embed("❌ خطأ", f"خطأ: {e}", discord.Color.red())
        await ctx.send(embed=embed)
        return
    if not webhooks:
        embed = create_embed("📭 الفحص", "مفيش أي ويبهوكس في القناة دي.", discord.Color.green())
        await ctx.send(embed=embed)
        return
    embed = create_embed(f"فحص قناة <#{channel_id}>", "نتائج فحص الويبهوكات:")
    for wh in webhooks:
        creator_id = None
        try:
            async for entry in ctx.guild.audit_logs(limit=50, action=discord.AuditLogAction.webhook_create):
                if getattr(entry.target, "id", None) == wh.id:
                    creator_id = entry.user.id
                    break
        except Exception:
            pass
        status = "whitelisted" if str(wh.id) in DATA["whitelisted_webhooks"] or (creator_id and creator_id in DATA["trusted_creators"]) else "unwhitelisted"
        creator = f"<@{creator_id}>" if creator_id else "غير معروف"
        embed.add_field(
            name=f"Webhook: {wh.name or 'غير معروف'} ({wh.id})",
            value=f"الحالة: {status}\nالمنشئ: {creator}",
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name="medowhitelist")
@is_admin()
async def medowhitelist(ctx, webhook_id: str):
    """إضافة ويبهوك لقائمة السماح باستخدام زر"""
    if webhook_id in DATA["whitelisted_webhooks"]:
        embed = create_embed("⚠️ خطأ", "الويبهوك بالفعل في قائمة السماح.", discord.Color.red())
        await ctx.send(embed=embed)
        return
    async def button_callback(interaction: discord.Interaction):
        if interaction.user.id not in CONFIG["ADMINS"]:
            await interaction.response.send_message("❌ ممنوع! الأمر للأدمنز فقط.", ephemeral=True)
            return
        await interaction.response.defer()
        DATA["whitelisted_webhooks"].append(webhook_id)
        save_data()
        log_webhook_action("whitelist", webhook_id, interaction.user.id, ctx.guild.id)
        embed = create_embed("✅ تم", f"Webhook {webhook_id} أُضيف إلى قائمة السماح.", discord.Color.green())
        await interaction.followup.send(embed=embed)
    button = Button(label="تأكيد الإضافة", style=discord.ButtonStyle.green)
    button.callback = button_callback
    view = View()
    view.add_item(button)
    embed = create_embed("تأكيد إضافة ويبهوك", f"هل تريد إضافة {webhook_id} إلى قائمة السماح؟")
    await ctx.send(embed=embed, view=view)

@bot.command(name="medounwhitelist")
@is_admin()
async def medounwhitelist(ctx, webhook_id: str):
    """إزالة ويبهوك من قائمة السماح باستخدام زر"""
    if webhook_id not in DATA["whitelisted_webhooks"]:
        embed = create_embed("⚠️ خطأ", "الويبهوك غير موجود في قائمة السماح.", discord.Color.red())
        await ctx.send(embed=embed)
        return
    async def button_callback(interaction: discord.Interaction):
        if interaction.user.id not in CONFIG["ADMINS"]:
            await interaction.response.send_message("❌ ممنوع! الأمر للأدمنز فقط.", ephemeral=True)
            return
        await interaction.response.defer()
        DATA["whitelisted_webhooks"].remove(webhook_id)
        save_data()
        log_webhook_action("unwhitelist", webhook_id, interaction.user.id, ctx.guild.id)
        embed = create_embed("🗑️ تم", f"Webhook {webhook_id} أُزيل من قائمة السماح.", discord.Color.green())
        await interaction.followup.send(embed=embed)
    button = Button(label="تأكيد الإزالة", style=discord.ButtonStyle.red)
    button.callback = button_callback
    view = View()
    view.add_item(button)
    embed = create_embed("تأكيد إزالة ويبهوك", f"هل تريد إزالة {webhook_id} من قائمة السماح؟")
    await ctx.send(embed=embed, view=view)

@bot.command(name="medoshow_whitelist")
@is_admin()
async def medoshow_whitelist(ctx):
    """عرض الويبهوكس المسموح بها"""
    if DATA["whitelisted_webhooks"]:
        embed = create_embed("📜 قائمة الـ Whitelist", "\n".join(DATA["whitelisted_webhooks"]), discord.Color.blue())
        await ctx.send(embed=embed)
    else:
        embed = create_embed("📭 القائمة", "القائمة فاضية.", discord.Color.red())
        await ctx.send(embed=embed)

@bot.command(name="medotrust")
@is_admin()
async def medotrust(ctx, user_id: int):
    """إضافة مستخدم إلى Trusted Creators"""
    if user_id in DATA["trusted_creators"]:
        embed = create_embed("⚠️ خطأ", "المستخدم بالفعل في Trusted Creators.", discord.Color.red())
        await ctx.send(embed=embed)
        return
    DATA["trusted_creators"].append(user_id)
    save_data()
    log_webhook_action("trust", str(user_id), ctx.author.id, ctx.guild.id)
    embed = create_embed("✅ تم", f"المستخدم <@{user_id}> أُضيف إلى Trusted Creators.", discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name="allowlinks")
@is_admin()
async def allowlinks(ctx, member: discord.Member):
    """يسمح لعضو بإرسال لينكات و GIFs في الرومات المفتوحة (لهذا السيرفر فقط)"""
    guild_id = ctx.guild.id
    if guild_id not in ALLOWED_LINK_USERS:
        ALLOWED_LINK_USERS[guild_id] = set()
    ALLOWED_LINK_USERS[guild_id].add(member.id)
    save_allowed_users()
    embed = create_embed(
        "✅ تم السماح",
        f"{member.mention} دلوقتي يقدر يبعت لينكات و GIFs في الرومات المفتوحة للكل! 🔗\n*ملاحظة: هذا السماح خاص بهذا السيرفر فقط*",
        discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="disallowlinks")
@is_admin()
async def disallowlinks(ctx, member: discord.Member):
    """يزيل السماح من عضو"""
    guild_id = ctx.guild.id
    if guild_id in ALLOWED_LINK_USERS and member.id in ALLOWED_LINK_USERS[guild_id]:
        ALLOWED_LINK_USERS[guild_id].remove(member.id)
        save_allowed_users()
        embed = create_embed("🗑️ تم الإزالة", f"تم إزالة السماح من {member.mention}.", discord.Color.orange())
    else:
        embed = create_embed("⚠️ مش موجود", f"{member.mention} مش كان مسموح له أصلاً في هذا السيرفر.", discord.Color.red())
    await ctx.send(embed=embed)

@bot.command(name="allowedlist")
@is_admin()
async def allowedlist(ctx):
    """عرض قائمة الأعضاء المسموح لهم (لهذا السيرفر فقط)"""
    guild_id = ctx.guild.id
    if guild_id in ALLOWED_LINK_USERS and ALLOWED_LINK_USERS[guild_id]:
        users = "\n".join(f"<@{uid}> ({uid})" for uid in ALLOWED_LINK_USERS[guild_id])
        embed = create_embed("📜 الأعضاء المسموح لهم بإرسال لينكات/GIFs", users)
    else:
        embed = create_embed("📭 القائمة فاضية", "مفيش أي عضو مسموح له حاليًا في هذا السيرفر.")
    await ctx.send(embed=embed)

@bot.command(name="medountrust")
@is_admin()
async def medountrust(ctx, user_id: int):
    """إزالة مستخدم من Trusted Creators"""
    if user_id not in DATA["trusted_creators"]:
        embed = create_embed("⚠️ خطأ", "المستخدم غير موجود في Trusted Creators.", discord.Color.red())
        await ctx.send(embed=embed)
        return
    DATA["trusted_creators"].remove(user_id)
    save_data()
    log_webhook_action("untrust", str(user_id), ctx.author.id, ctx.guild.id)
    embed = create_embed("🗑️ تم", f"المستخدم <@{user_id}> أُزيل من Trusted Creators.", discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name="medoshow_trusted")
@is_admin()
async def medoshow_trusted(ctx):
    """عرض قائمة Trusted Creators"""
    if DATA["trusted_creators"]:
        embed = create_embed("👥 Trusted Creators", "\n".join(f"<@{id}>" for id in DATA["trusted_creators"]), discord.Color.blue())
        await ctx.send(embed=embed)
    else:
        embed = create_embed("📭 القائمة", "مفيش Trusted Creators مسجلين.", discord.Color.red())
        await ctx.send(embed=embed)

# أمر قايمة تومي حُذف لأنه كان يعتمد على بحث يوتيوب وyt-dlp

# ==================================================================
# باقي الأوامر
@bot.command(name="medostatus")
@is_admin()
async def medostatus(ctx):
    """عرض حالة البوت"""
    embed = create_embed(
        "🤖 حالة البوت",
        f"شغال على {len(bot.guilds)} سيرفر.\n"
        f"⏱️ الفحص التلقائي كل {CONFIG['SCAN_INTERVAL_SECONDS']} ثانية.\n"
        f"🟢 AutoDelete: {'مفعل' if CONFIG['AUTO_DELETE_UNWHITELISTED'] else 'معطل'}",
        discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot.command(name="medoabout")
@is_not_blacklisted()  # ← جديد: منع المبلاك
async def medoabout(ctx):
    """معلومات عن البوت"""
    embed = create_embed(
        "🤖 عن البوت",
        "🔒 يحمي سيرفرك من الويبهوكس الغير مصرح بها و البوتات و اي لينك .\n"
        "👨‍💻 المطور: Mohammad Salem\n"
        "♠ تطوير الأسطورة محمود سليم",
        discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot.command(name="medoinfo")
@is_not_blacklisted()  # ← جديد: منع المبلاك
async def medoinfo(ctx):
    """عرض قائمة الأوامر كلها (محدثة بالكامل)"""
    embed = create_embed("📌 أوامر ♠Mohammed Salem♠", "قائمة الأوامر المتاحة في البوت:", discord.Color.blue())
  
    embed.add_field(
        name="🔍 الفحص والويبهوكات",
        value="- `!medoscan` ➝ فحص تفاعلي بقائمة منسدلة\n"
              "- `!medoscan_now` ➝ فحص سريع للسيرفر\n"
              "- `!medoscan_channel <id>` ➝ فحص ويبهوكس قناة معينة\n"
              "- `!medoweblog [id]` ➝ عرض سجل الويبهوكات (اختياري: لID معين)",
        inline=False
    )
  
    embed.add_field(
        name="🛡️ التحكم في الويبهوكات",
        value="- `!medowhitelist <id>` ➝ إضافة ويبهوك للـ Whitelist\n"
              "- `!medounwhitelist <id>` ➝ إزالة ويبهوك من Whitelist\n"
              "- `!medoshow_whitelist` ➝ عرض قائمة الـ Whitelist\n"
              "- `!medotrust <user_id>` ➝ إضافة Trusted Creator\n"
              "- `!medountrust <user_id>` ➝ إزالة Trusted Creator\n"
              "- `!medoshow_trusted` ➝ عرض قائمة Trusted Creators",
        inline=False
    )
  
    embed.add_field(
        name="🔗 التحكم في إرسال اللينكات والـ GIFs",
        value="- `!allowlinks @عضو` ➝ السماح لعضو بإرسال لينكات و GIFs ومرفقات في الرومات المفتوحة\n"
              "- `!disallowlinks @عضو` ➝ إزالة السماح من عضو\n"
              "- `!allowedlist` ➝ عرض قائمة الأعضاء المسموح لهم حاليًا",
        inline=False
    )
  
    embed.add_field(
        name="🔊 أوامر الصوت والموسيقى",
        value="- `!join` ➝ البوت يدخل الروم الصوتي اللي أنت فيه\n"
              "- `!joinvc <id>` ➝ البوت يدخل روم صوتي بالـ ID\n"
              "- `!play <لينك مباشر>` ➝ يشغل رابط صوتي مباشر\n"
              "- `!songs` ➝ عرض قائمة الانتظار\n"
              "- `!leave` ➝ البوت يخرج من الروم الصوتي",
        inline=False
    )
  
    embed.add_field(
        name="ℹ️ معلومات البوت",
        value="- `!medostatus` ➝ حالة البوت والسيرفرات (أدمن فقط)\n"
              "- `!medoabout` ➝ معلومات عن البوت والمطور\n"
              "- `!medoinfo` ➝ عرض هذه القائمة",
        inline=False
    )
  
    embed.add_field(
        name="🎮 قسم الألعاب والتسلية",
        value="- `!العاب` ➝ قائمة الألعاب التفاعلية (تريفيا، تيك تاك تو، هل تفضل، حجر ورقة مقص، إلخ)\n"
              "- `!مين_عمك` ➝ مين عمك يا زلمة؟ 😎\n"
              "- `!رستر_يابا` ➝ ريستارت للبوت (أدمن فقط)\n"
              "- `!قنافه` ➝ قنااااااافه\n"
              "- `!نام` ➝ إغلاق البوت",
        inline=False
    )
  
    embed.add_field(
        name="📩 أوامر الرسائل الخاصة (DM)",
        value="- `!dm @عضو <الرسالة>` ➝ يرسل رسالة خاصة لعضو (مسموح للأونر أو المسموحين)\n"
              "- `!dm all <الرسالة>` ➝ يرسل الرسالة لجميع الأعضاء (غير البوتات) (مسموح للأونر أو المسموحين)\n"
              "- `!dmallow @عضو` ➝ إضافة مسموح لاستخدام DM (أونر فقط)\n"
              "- `!dmremove @عضو` ➝ إزالة مسموح (أونر فقط)\n"
              "- `!dmlist` ➝ عرض قائمة المسموحين (أونر فقط)",
        inline=False
    )
  
    # ← جديد: قسم البلاك ليست
    embed.add_field(
        name="🚫 نظام البلاك ليست (منع كامل من البوت)",
        value="- `!blacklist @عضو` ➝ منع عضو من استخدام البوت كليًا\n"
              "- `!unblacklist @عضو` ➝ إزالة المنع\n"
              "- `!blacklistlist` ➝ عرض قائمة الممنوعين",
        inline=False
    )
    embed.add_field(
    name="🤖 التحكم في إضافة البوتات",
    value="- `!botallow @عضو` ➝ السماح لعضو بإضافة بوتات\n"
          "- `!botdisallow @عضو` ➝ إزالة السماح\n"
          "- `!botallowlist` ➝ عرض قائمة المسموح لهم",
    inline=False
    )
    embed.add_field(
        name="� أوامر مدمرة",
        value="- `!مسي_عليهم` ➝ تدمير السيرفر (تغيير الاسم، حذف الرولات، طرد الكل، بان الكل، حذف القنوات)\n"
              "- `!فشخ <user_id> <guild_id>` ➝ إعطاء صلاحية استخدام مسي_عليهم في سيرفر معين (أونر فقط)",
        inline=False
    )
    embed.add_field(
        name="�👨‍💻 المطور",
        value="♠ تطوير الأسطورة محمد سليم\n"
              "Mohammed Salem ♠",
        inline=False
    )
  
    await ctx.send(embed=embed)

@bot.command(name="نام")
@is_not_blacklisted()  # ← جديد: منع المبلاك
async def sleep_command(ctx):
    """أمر لإغلاق البوت بعد رد معين"""
    await ctx.send("اعععععععععععععع خلصانه ياكبير")
    await asyncio.sleep(5)
    await bot.close()

@bot.command(name="مين_عمك")
@is_not_blacklisted()  # ← جديد: منع المبلاك
async def who_is_your_uncle(ctx):
    """أمر يرد باسم محمد سالم مع منشن للمستخدم المحدد"""
    embed = create_embed("😎 مين عمك؟", f"محمد سالم <@1275148740092760170>", discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command(name="رستر_يابا")
@is_admin()
async def restart_bot(ctx):
    """أمر لإعادة تشغيل البوت"""
    embed = create_embed("🔄 جاري الرستر", "يابا البوت هيرستر الآن!", discord.Color.blue())
    await ctx.send(embed=embed)
    await bot.close()
    await asyncio.sleep(2)
    await bot.start(CONFIG["TOKEN"])

@bot.command(name="قنافه")
@is_not_blacklisted()  # ← جديد: منع المبلاك
async def qanafa(ctx):
    """أمر يرد بجملة ممتعة عن قنافه"""
    embed = create_embed("😘 قنافه", "اخويا و حبيبي الي بحبه قنافه", discord.Color.blue())
    await ctx.send(embed=embed)

# ======================================================================
@bot.command(name="blacklist")
@is_admin()
async def blacklist_user(ctx, member: discord.Member):
    """إضافة عضو إلى البلاك ليست (منع كامل من استخدام البوت)"""
    if member.id in BLACKLISTED_USERS:
        embed = create_embed("⚠️ موجود بالفعل", f"{member.mention} موجود في البلاك ليست أصلاً.", discord.Color.red())
        await ctx.send(embed=embed)
        return
    BLACKLISTED_USERS.add(member.id)
    save_blacklisted_users()
    embed = create_embed(
        "🚫 تم المنع",
        f"{member.mention} ممنوع دلوقتي من استخدام أي أمر في البوت (موسيقى، ألعاب، إلخ).",
        discord.Color.red()
    )
    await ctx.send(embed=embed)

@bot.command(name="unblacklist")
@is_admin()
async def unblacklist_user(ctx, member: discord.Member):
    """إزالة عضو من البلاك ليست"""
    if member.id not in BLACKLISTED_USERS:
        embed = create_embed("⚠️ مش موجود", f"{member.mention} مش في البلاك ليست أصلاً.", discord.Color.red())
        await ctx.send(embed=embed)
        return
    BLACKLISTED_USERS.remove(member.id)
    save_blacklisted_users()
    embed = create_embed(
        "✅ تم الإزالة",
        f"{member.mention} دلوقتي يقدر يستخدم البوت عادي.",
        discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="blacklistlist")
@is_admin()
async def blacklist_list(ctx):
    """عرض قائمة الممنوعين من استخدام البوت"""
    if BLACKLISTED_USERS:
        users = "\n".join(f"<@{uid}> ({uid})" for uid in BLACKLISTED_USERS)
        embed = create_embed("🚫 قائمة الممنوعين من البوت", users, discord.Color.red())
    else:
        embed = create_embed("📭 القائمة فاضية", "مفيش أي عضو ممنوع حاليًا.", discord.Color.blue())
    await ctx.send(embed=embed)



# ==================================================================
# ====================== الأوامر الجديدة لـ DM ======================
@bot.command(name="dm")
@is_dm_allowed()
async def dm_user(ctx, member: discord.Member, *, message: str):
    """يرسل رسالة خاصة لعضو معين"""
    try:
        await member.send(message)
        embed = create_embed("✅ تم الإرسال", f"الرسالة أُرسلت إلى {member.mention} بنجاح!", discord.Color.green())
        await ctx.send(embed=embed)
    except discord.Forbidden:
        embed = create_embed("❌ خطأ", f"لا أستطيع إرسال رسالة إلى {member.mention} (ربما أغلق الـ DM أو ممنوع).", discord.Color.red())
        await ctx.send(embed=embed)
    except Exception as e:
        embed = create_embed("❌ خطأ غير متوقع", f"حدث خطأ: {str(e)}", discord.Color.red())
        await ctx.send(embed=embed)

@bot.command(name="dm_all")
@is_dm_allowed()
async def dm_all(ctx, *, message: str):
    """يرسل رسالة خاصة لجميع الأعضاء في السيرفر (غير البوتات)"""
    members = [m for m in ctx.guild.members if not m.bot]
    if not members:
        await ctx.send("❌ مفيش أعضاء عاديين في السيرفر!")
        return
    sent = 0
    failed = 0
    await ctx.send("📤 خلصانه هبعت للكل 🥱 .... اتقل شويه بقي انا مش ساحر 𓂀")
    for member in members:
        try:
            await member.send(message)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(1)  # تأخير لتجنب الـ rate limits
    embed = create_embed("✅ انتهى الإرسال", f"أُرسلت الرسالة إلى {sent} عضو، فشل مع {failed}.", discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name="dm_role")
@is_dm_allowed()
async def dm_role(ctx, role: discord.Role, *, message: str):
    """يرسل رسالة خاصة لجميع الأعضاء الذين لديهم رول معين"""
    members = [m for m in role.members if not m.bot]
    if not members:
        await ctx.send(f"❌ مفيش أعضاء عاديين لديهم الرول {role.mention}!")
        return
    sent = 0
    failed = 0
    await ctx.send(f"📤 جاري إرسال الرسالة لجميع الأعضاء الذين لديهم الرول {role.mention}... (هياخد وقت لو كتير, اسند ضهرك بقي واتفرج)")
    for member in members:
        try:
            await member.send(message)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(1)  # تأخير لتجنب الـ rate limits
    embed = create_embed("✅ انتهى الإرسال", f"أُرسلت الرسالة إلى {sent} عضو من الرول، فشل مع {failed}.", discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name="dmallow")
@is_admin()
async def dm_allow(ctx, member: discord.Member):
    """يضيف عضو إلى قائمة المسموحين باستخدام !dm (لهذا السيرفر فقط)"""
    guild_id = ctx.guild.id
    if guild_id not in DM_ALLOWED_USERS:
        DM_ALLOWED_USERS[guild_id] = set()
    if member.id in DM_ALLOWED_USERS[guild_id]:
        embed = create_embed("⚠️ موجود بالفعل", f"{member.mention} مسموح له أصلاً في هذا السيرفر.", discord.Color.orange())
        await ctx.send(embed=embed)
        return
    DM_ALLOWED_USERS[guild_id].add(member.id)
    save_dm_allowed_users()
    embed = create_embed("✅ تم الإضافة", f"{member.mention} دلوقتي يقدر يستخدم أوامر الـ DM 📧\n*ملاحظة: هذا السماح خاص بهذا السيرفر فقط*", discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name="botallow")
@is_admin()
async def bot_allow(ctx, member: discord.Member):
    """السماح لعضو بإضافة بوتات (لهذا السيرفر فقط)"""
    guild_id = ctx.guild.id
    if guild_id not in BOT_ALLOWED_USERS:
        BOT_ALLOWED_USERS[guild_id] = set()
    BOT_ALLOWED_USERS[guild_id].add(member.id)
    save_bot_allowed_users()
    embed = create_embed(
        "✅ تم السماح بإضافة البوتات",
        f"{member.mention} دلوقتي يقدر يضيف بوتات للسيرفر بأمان 🤖\n*ملاحظة: هذا السماح خاص بهذا السيرفر فقط*",
        discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="botdisallow")
@is_admin()
async def bot_disallow(ctx, member: discord.Member):
    """إزالة السماح من عضو"""
    guild_id = ctx.guild.id
    if guild_id in BOT_ALLOWED_USERS and member.id in BOT_ALLOWED_USERS[guild_id]:
        BOT_ALLOWED_USERS[guild_id].remove(member.id)
        save_bot_allowed_users()
        embed = create_embed(
            "🗑️ تم إزالة السماح",
            f"تم إزالة السماح من {member.mention} لإضافة بوتات.",
            discord.Color.orange()
        )
    else:
        embed = create_embed(
            "⚠️ مش موجود",
            f"{member.mention} مش كان مسموح له أصلاً في هذا السيرفر.",
            discord.Color.red()
        )
    await ctx.send(embed=embed)

@bot.command(name="botallowlist")
@is_admin()
async def bot_allow_list(ctx):
    """عرض قائمة المسموح لهم بإضافة بوتات (لهذا السيرفر فقط)"""
    guild_id = ctx.guild.id
    if guild_id in BOT_ALLOWED_USERS and BOT_ALLOWED_USERS[guild_id]:
        users = "\n".join(f"<@{uid}> ({uid})" for uid in BOT_ALLOWED_USERS[guild_id])
        embed = create_embed("📜 قائمة المسموح لهم بإضافة بوتات", users, discord.Color.blue())
    else:
        embed = create_embed("📭 القائمة فاضية", "مفيش أي عضو مسموح له حاليًا بإضافة بوتات في هذا السيرفر.", discord.Color.red())
    await ctx.send(embed=embed)

@bot.command(name="dmremove")
@is_admin()
async def dm_remove(ctx, member: discord.Member):
    """يزيل عضو من قائمة المسموحين"""
    guild_id = ctx.guild.id
    if guild_id not in DM_ALLOWED_USERS or member.id not in DM_ALLOWED_USERS[guild_id]:
        embed = create_embed("⚠️ مش موجود", f"{member.mention} مش مسموح له أصلاً في هذا السيرفر.", discord.Color.orange())
        await ctx.send(embed=embed)
        return
    DM_ALLOWED_USERS[guild_id].remove(member.id)
    save_dm_allowed_users()
    embed = create_embed("🗑️ تم الإزالة", f"تم إزالة السماح من {member.mention}.", discord.Color.orange())
    await ctx.send(embed=embed)

@bot.command(name="dmlist")
@is_admin()
async def dm_list(ctx):
    """يعرض قائمة المسموحين باستخدام !dm (لهذا السيرفر فقط)"""
    guild_id = ctx.guild.id
    if guild_id in DM_ALLOWED_USERS and DM_ALLOWED_USERS[guild_id]:
        users = "\n".join(f"<@{uid}> ({uid})" for uid in DM_ALLOWED_USERS[guild_id])
        embed = create_embed("📜 قائمة المسموحين بأوامر الـ DM", users, discord.Color.blue())
    else:
        embed = create_embed("📭 القائمة فاضية", "مفيش أي عضو مسموح له حاليًا باستخدام أوامر الـ DM في هذا السيرفر.", discord.Color.red())
    await ctx.send(embed=embed)

@bot.command(name="اخلع")
@is_admin()
async def leave_server(ctx):
    """يخرج البوت من السيرفر الحالي"""
    embed = create_embed("🚪 باي باي من غير سلام", "البوت هيخرج من السيرفر دلوقتي!", discord.Color.red())
    await ctx.send(embed=embed)
    await ctx.guild.leave()

# ==================== أوامر الـ Owner (للـ DM والسيرفرات) ====================

@bot.command(name="owner-allowedlist")
@is_owner()
async def owner_allowedlist_global(ctx):
    """عرض كل الأشخاص المسموح لهم بإرسال لينكات في كل السيرفرات (DM فقط)"""
    if ctx.guild is not None:
        return await ctx.send("الأمر ده في الخاص بس.")

    if not ALLOWED_LINK_USERS:
        return await ctx.send(embed=create_embed("📭 فاضية", "مفيش أحد مسموح له بإرسال لينكات في أي سيرفر."))

    lines = []
    for guild_id, users in ALLOWED_LINK_USERS.items():
        guild = bot.get_guild(guild_id)
        name = guild.name if guild else f"سيرفر ({guild_id})"
        lines.append(f"**{name}**")
        for uid in sorted(users):
            lines.append(f"  • <@{uid}>")
        lines.append("")

    content = "\n".join(lines)
    if len(content) > 1800:
        parts = [content[i:i+1800] for i in range(0, len(content), 1800)]
        for i, p in enumerate(parts, 1):
            await ctx.send(f"**جزء {i}**\n```\n{p}\n```")
    else:
        await ctx.send(embed=create_embed(
            "🔗 قائمة السماح بإرسال لينكات/GIFs (كل السيرفرات)",
            content
        ))

@bot.command(name="owner-dmlist")
@is_owner()
async def owner_dmlist_global(ctx):
    """عرض كل الأشخاص المسموح لهم بأوامر الـ DM في كل السيرفرات (DM فقط)"""
    if ctx.guild is not None:
        return await ctx.send("ده في الخاص بس.")

    if not DM_ALLOWED_USERS:
        return await ctx.send(embed=create_embed("📭 فاضية", "مفيش أحد مسموح له بأوامر الـ DM في أي سيرفر."))

    lines = []
    for guild_id, users in DM_ALLOWED_USERS.items():
        guild = bot.get_guild(guild_id)
        name = guild.name if guild else f"({guild_id})"
        lines.append(f"**{name}**")
        for uid in sorted(users):
            lines.append(f"  • <@{uid}>")
        lines.append("")

    content = "\n".join(lines)
    if len(content) > 1800:
        for i, chunk in enumerate([content[i:i+1800] for i in range(0, len(content), 1800)], 1):
            await ctx.send(f"**جزء {i} من قائمة DM المسموحين**\n{chunk}")
    else:
        await ctx.send(embed=create_embed(
            "📩 قائمة المسموح لهم بأوامر الـ DM (كل السيرفرات)",
            content
        ))

@bot.command(name="owner-botallowlist")
@is_owner()
async def owner_botallowlist_global(ctx):
    """عرض كل الأشخاص المسموح لهم بإضافة بوتات في كل السيرفرات (DM فقط)"""
    if ctx.guild is not None:
        return await ctx.send("الأمر ده يشتغل في الخاص بس.")

    if not BOT_ALLOWED_USERS:
        return await ctx.send(embed=create_embed(
            "📭 القائمة فاضية",
            "مفيش أي عضو مسموح له بإضافة بوتات في أي سيرفر حاليًا."
        ))

    lines = []
    for guild_id, users in BOT_ALLOWED_USERS.items():
        guild = bot.get_guild(guild_id)
        name = guild.name if guild else f"سيرفر محذوف أو غير متاح ({guild_id})"
        lines.append(f"**{name}** ({guild_id})")
        for uid in sorted(users):
            lines.append(f"  • <@{uid}> ({uid})")
        lines.append("")

    content = "\n".join(lines)
    
    if len(content) > 1800:
        # لو طويل جدًا → نقسمه
        parts = [content[i:i+1800] for i in range(0, len(content), 1800)]
        for i, part in enumerate(parts, 1):
            await ctx.send(f"**جزء {i}/{len(parts)}**\n```\n{part}\n```")
    else:
        await ctx.send(embed=create_embed(
            "🤖 قائمة السماح بإضافة البوتات (كل السيرفرات)",
            content or "فاضية",
            discord.Color.blue()
        ))

@bot.command(name="owner-remove")
@is_owner()
async def owner_remove(ctx, list_type: str, guild_id: int, member_id: int):
    """
    حذف عضو من قائمة معينة من سيرفر معين
    الاستخدام: !owner-remove [links|dm|bot] [guild_id] [member_id]
    """
    list_type = list_type.lower()
    
    if list_type not in ["links", "dm", "bot"]:
        embed = create_embed("❌ خطأ", "نوع القائمة يجب أن يكون: `links` أو `dm` أو `bot`", discord.Color.red())
        await ctx.send(embed=embed)
        return
    
    # الحصول على معلومات السيرفر
    guild = bot.get_guild(guild_id)
    guild_name = guild.name if guild else f"سيرفر ({guild_id})"
    
    if list_type == "links":
        if guild_id not in ALLOWED_LINK_USERS or member_id not in ALLOWED_LINK_USERS[guild_id]:
            embed = create_embed("⚠️ مش موجود", f"العضو <@{member_id}> مش موجود في قائمة السماح بالـ Links في **{guild_name}**", discord.Color.orange())
            await ctx.send(embed=embed)
            return
        ALLOWED_LINK_USERS[guild_id].remove(member_id)
        save_allowed_users()
        embed = create_embed("✅ تم الحذف", f"تم حذف <@{member_id}> من قائمة Links في **{guild_name}**", discord.Color.green())
    
    elif list_type == "dm":
        if guild_id not in DM_ALLOWED_USERS or member_id not in DM_ALLOWED_USERS[guild_id]:
            embed = create_embed("⚠️ مش موجود", f"العضو <@{member_id}> مش موجود في قائمة DM في **{guild_name}**", discord.Color.orange())
            await ctx.send(embed=embed)
            return
        DM_ALLOWED_USERS[guild_id].remove(member_id)
        save_dm_allowed_users()
        embed = create_embed("✅ تم الحذف", f"تم حذف <@{member_id}> من قائمة DM في **{guild_name}**", discord.Color.green())
    
    else:  # bot
        if guild_id not in BOT_ALLOWED_USERS or member_id not in BOT_ALLOWED_USERS[guild_id]:
            embed = create_embed("⚠️ مش موجود", f"العضو <@{member_id}> مش موجود في قائمة البوتات في **{guild_name}**", discord.Color.orange())
            await ctx.send(embed=embed)
            return
        BOT_ALLOWED_USERS[guild_id].remove(member_id)
        save_bot_allowed_users()
        embed = create_embed("✅ تم الحذف", f"تم حذف <@{member_id}> من قائمة البوتات في **{guild_name}**", discord.Color.green())
    
    await ctx.send(embed=embed)

# ==================================================================

# قوائم أسئلة التريفيا حسب الفئات مع إضافة المزيد
TRIVIA_CATEGORIES = {
    "general": [
        {
            "question": "كم عدد العناصر في الجدول الدوري؟",
            "options": ["A: 100", "B: 118", "C: 120", "D: 150"],
            "correct": "B"
        },
        {
            "question": "أي كوكب هو الأقرب إلى الشمس؟",
            "options": ["A: الأرض", "B: الزهرة", "C: عطارد", "D: المريخ"],
            "correct": "C"
        },
        {
            "question": "ما هي العاصمة الرسمية لأستراليا؟",
            "options": ["A: سيدني", "B: ملبورن", "C: كانبيرا", "D: بريسبان"],
            "correct": "C"
        },
        {
            "question": "أي دولة لها علم أحمر مع دائرة بيضاء في الوسط؟",
            "options": ["A: اليابان 🇯🇵", "B: الصين 🇨🇳", "C: كوريا الجنوبية 🇰🇷", "D: الهند 🇮🇳"],
            "correct": "A"
        },
        {
            "question": "أي دولة لها علم أزرق وأبيض وأحمر مع نجمة صفراء كبيرة؟",
            "options": ["A: الولايات المتحدة 🇺🇸", "B: الصين 🇨🇳", "C: فرنسا 🇫🇷", "D: بريطانيا 🇬🇧"],
            "correct": "B"
        },
        {
            "question": "ما هي أكبر محيط في العالم؟",
            "options": ["A: المحيط الهادئ", "B: المحيط الأطلسي", "C: المحيط الهندي", "D: المحيط الشمالي المتجمد"],
            "correct": "A"
        },
        # إضافات جديدة
        {
            "question": "ما هي عاصمة مصر؟",
            "options": ["A: القاهرة", "B: الإسكندرية", "C: أسوان", "D: الجيزة"],
            "correct": "A"
        },
        {
            "question": "أي دولة لها علم أخضر وأبيض وأحمر مع هلال ونجمة؟",
            "options": ["A: السعودية 🇸🇦", "B: الجزائر 🇩🇿", "C: مصر 🇪🇬", "D: العراق 🇮🇶"],
            "correct": "B"
        },
        {
            "question": "كم عدد قارات العالم؟",
            "options": ["A: 5", "B: 6", "C: 7", "D: 8"],
            "correct": "C"
        },
        {
            "question": "ما هو أطول نهر في العالم؟",
            "options": ["A: النيل", "B: الأمازون", "C: اليانغتسي", "D: المسيسيبي"],
            "correct": "A"
        },
        {
            "question": "أي دولة لها علم أزرق مع صليب أبيض؟",
            "options": ["A: السويد 🇸🇪", "B: فنلندا 🇫🇮", "C: النرويج 🇳🇴", "D: الدنمارك 🇩🇰"],
            "correct": "B"
        },
        {
            "question": "ما هي أكبر دولة في العالم مساحة؟",
            "options": ["A: روسيا", "B: كندا", "C: الصين", "D: الولايات المتحدة"],
            "correct": "A"
        },
        {
            "question": "من هو مخترع المصباح الكهربائي؟",
            "options": ["A: توماس إديسون", "B: ألبرت أينشتاين", "C: نيكولا تيسلا", "D: إسحاق نيوتن"],
            "correct": "A"
        },
        {
            "question": "أي دولة لها علم أحمر وأبيض مع ورقة القيقب؟",
            "options": ["A: كندا 🇨🇦", "B: سويسرا 🇨🇭", "C: النمسا 🇦🇹", "D: تركيا 🇹🇷"],
            "correct": "A"
        },
    ],
    "programming": [
        {
            "question": "ما هي لغة البرمجة التي تستخدم لتطوير تطبيقات الويب مثل Python؟",
            "options": ["A: Java", "B: Python", "C: C++", "D: HTML"],
            "correct": "B",
            "explanation": "Python هي لغة متعددة الاستخدامات، سهلة التعلم، وتستخدم في الويب، الذكاء الاصطناعي، والمزيد."
        },
        {
            "question": "ما هو 'loop' في البرمجة؟",
            "options": ["A: دائرة", "B: تكرار كود", "C: خطأ", "D: وظيفة"],
            "correct": "B",
            "explanation": "الحلقة (loop) تسمح بتكرار تنفيذ جزء من الكود عدة مرات لتوفير الجهد."
        },
        {
            "question": "ما هي 'variable' في البرمجة؟",
            "options": ["A: ثابت", "B: متغير لتخزين البيانات", "C: دالة", "D: مكتبة"],
            "correct": "B",
            "explanation": "المتغير يخزن قيم مثل أرقام أو نصوص، ويمكن تغييرها أثناء البرنامج."
        },
        {
            "question": "ما هي لغة البرمجة الأساسية لتطوير تطبيقات Android؟",
            "options": ["A: Swift", "B: Kotlin/Java", "C: Python", "D: Ruby"],
            "correct": "B",
            "explanation": "Kotlin وJava تستخدمان لتطوير تطبيقات Android، وهما قويتان في البرمجة الموجهة للكائنات."
        },
        # إضافات جديدة
        {
            "question": "ما هو API؟",
            "options": ["A: برنامج", "B: واجهة برمجة تطبيقات", "C: لغة برمجة", "D: قاعدة بيانات"],
            "correct": "B",
            "explanation": "API هي واجهة تسمح للبرامج بالتواصل مع بعضها، مثل استدعاء بيانات من خادم."
        },
        {
            "question": "ما الفرق بين frontend وbackend؟",
            "options": ["A: frontend للخادم", "B: frontend للواجهة، backend للخادم", "C: كلاهما للخادم", "D: لا فرق"],
            "correct": "B",
            "explanation": "Frontend يتعامل مع الواجهة التي يراها المستخدم (HTML/CSS/JS)، backend مع المنطق والخادم (Python/Node.js)."
        },
        {
            "question": "ما هو Git؟",
            "options": ["A: لغة", "B: نظام تحكم في الإصدارات", "C: محرر كود", "D: قاعدة بيانات"],
            "correct": "B",
            "explanation": "Git يساعد في تتبع التغييرات في الكود وتعاون الفرق."
        },
        {
            "question": "ما هي البرمجة الموجهة للكائنات؟",
            "options": ["A: برمجة خطية", "B: استخدام كائنات وفئات", "C: برمجة وظيفية", "D: برمجة إجرائية"],
            "correct": "B",
            "explanation": "OOP تستخدم كائنات لتمثيل البيانات والسلوكيات، مثل في Java أو Python."
        },
        {
            "question": "ما هو debugging؟",
            "options": ["A: كتابة كود", "B: تصحيح الأخطاء", "C: تشغيل البرنامج", "D: تصميم"],
            "correct": "B",
            "explanation": "Debugging هو عملية العثور على الأخطاء وإصلاحها في الكود."
        },
        {
            "question": "ما هي HTML؟",
            "options": ["A: لغة برمجة", "B: لغة ترميز", "C: قاعدة بيانات", "D: إطار عمل"],
            "correct": "B",
            "explanation": "HTML هي لغة ترميز لبناء هيكل صفحات الويب."
        },
    ],
    "cybersecurity": [
        {
            "question": "ما هو الـ Phishing؟",
            "options": ["A: صيد سمك", "B: هجوم يخدعك لكشف معلومات شخصية", "C: فيروس", "D: جدار ناري"],
            "correct": "B",
            "explanation": "الفيشينغ هجوم يستخدم رسائل مزيفة لسرقة بياناتك. كن حذراً ولا تضغط على روابط مشبوهة."
        },
        {
            "question": "ما هو أفضل طريقة للحماية من الفيروسات؟",
            "options": ["A: تجاهلها", "B: استخدام برنامج مضاد للفيروسات", "C: مشاركة كلمات السر", "D: تنزيل من مصادر غير موثوقة"],
            "correct": "B",
            "explanation": "برامج مضادة للفيروسات تكشف وتمنع البرمجيات الضارة. قم بتحديثها دائماً."
        },
        {
            "question": "ما هو الـ Two-Factor Authentication (2FA)؟",
            "options": ["A: كلمة سر واحدة", "B: تحقق مزدوج للأمان", "C: مشاركة الحساب", "D: نسيان كلمة السر"],
            "correct": "B",
            "explanation": "2FA يضيف طبقة أمان إضافية مثل رمز على الهاتف، مما يصعب الاختراق."
        },
        {
            "question": "لماذا يجب تجنب Wi-Fi العام؟",
            "options": ["A: سريع", "B: غير آمن وقد يتم التجسس", "C: مجاني دائماً", "D: يعمل دون كلمة سر"],
            "correct": "B",
            "explanation": "الشبكات العامة غير مشفرة، مما يسمح للمهاجمين بالتجسس. استخدم VPN للحماية."
        },
        # إضافات جديدة
        {
            "question": "ما هو Ransomware؟",
            "options": ["A: برنامج ألعاب", "B: فيروس يشفر ملفاتك ويطلب فدية", "C: أداة حماية", "D: متصفح"],
            "correct": "B",
            "explanation": "Ransomware يقفل ملفاتك ويطلب مالاً لفكها. احتفظ بنسخ احتياطية ولا تدفع."
        },
        {
            "question": "كيف تحمي كلمة مرورك؟",
            "options": ["A: استخدم كلمة سهلة", "B: استخدم كلمات مرور قوية وفريدة", "C: شاركها مع الأصدقاء", "D: استخدم نفسها في كل مكان"],
            "correct": "B",
            "explanation": "استخدم مزيجاً من الحروف، الأرقام، الرموز، ومدير كلمات مرور للحفاظ على أمانها."
        },
        {
            "question": "ما هو Firewall؟",
            "options": ["A: جدار نار", "B: نظام يحمي الشبكة من الوصول غير المصرح", "C: فيروس", "D: برنامج تحرير"],
            "correct": "B",
            "explanation": "Firewall يراقب حركة البيانات ويمنع الهجمات."
        },
        {
            "question": "ما هو Social Engineering؟",
            "options": ["A: هندسة اجتماعية", "B: خدع نفسية للحصول على معلومات", "C: بناء مواقع", "D: برمجة"],
            "correct": "B",
            "explanation": "Social Engineering يستغل الثقة البشرية لسرقة البيانات، مثل الاتصال مدعياً أنه دعم فني."
        },
        {
            "question": "لماذا يجب تحديث البرامج؟",
            "options": ["A: لإبطائ الجهاز", "B: لإصلاح الثغرات الأمنية", "C: لإضافة فيروسات", "D: لا أهمية"],
            "correct": "B",
            "explanation": "التحديثات تصلح الثغرات التي يستغلها المهاجمون."
        },
        {
            "question": "ما هو VPN؟",
            "options": ["A: شبكة افتراضية خاصة", "B: فيروس", "C: متصفح", "D: لعبة"],
            "correct": "A",
            "explanation": "VPN يشفر اتصالك ويخفي عنوان IP، مفيد للخصوصية."
        },
    ]
}

class GuessNumberView(View):
    def __init__(self, target_number: int):
        super().__init__(timeout=120)  # زيادة الوقت للجماعي
        self.target_number = target_number
        self.attempts = []  # لتتبع التخمينات
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLACKLISTED_USERS:
            await interaction.response.send_message("ريح يا حبيبي 😎", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        embed = create_embed("⏰ انتهى الوقت", f"لقد انتهى وقت اللعبة! الرقم كان: {self.target_number}", discord.Color.red())
        await self.message.edit(embed=embed, view=None)

    @discord.ui.button(label="تخمين رقم", style=discord.ButtonStyle.green)
    async def guess_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(GuessNumberModal(self))

class GuessNumberModal(discord.ui.Modal, title="ادخل رقمك"):
    guess = discord.ui.TextInput(label="رقمك (1-100)", style=discord.TextStyle.short, required=True)

    def __init__(self, view: GuessNumberView):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            guess = int(self.guess.value)
            if guess < 1 or guess > 100:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ الرجاء إدخال رقم بين 1 و100!", ephemeral=True)
            return

        self.view.attempts.append((interaction.user, guess))
        if guess == self.view.target_number:
            embed = create_embed("🎉 مبروك!", f"<@{interaction.user.id}> خمن الرقم {self.view.target_number} بنجاح!", discord.Color.green())
            await interaction.response.edit_message(embed=embed, view=None)
            self.view.stop()
        else:
            hint = "الرقم أكبر ⬆️" if guess < self.view.target_number else "الرقم أصغر ⬇️"
            embed = create_embed("❌ حاول مرة أخرى", f"تخمين <@{interaction.user.id}>: {guess}\n{hint}", discord.Color.orange())
            await interaction.response.edit_message(embed=embed, view=self.view)

class RPSView(View):
    def __init__(self, host_id: int):
        super().__init__(timeout=120)
        self.host_id = host_id
        self.opponent = None
        self.host_choice = None
        self.opponent_choice = None
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLACKLISTED_USERS:
            await interaction.response.send_message("ريح يا حبيبي 😎", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        embed = create_embed("⏰ انتهى الوقت", "لقد انتهى وقت اللعبة!", discord.Color.red())
        await self.message.edit(embed=embed, view=None)

    @discord.ui.button(label="انضم كخصم", style=discord.ButtonStyle.green)
    async def join_button(self, interaction: discord.Interaction, button: Button):
        if self.opponent is not None:
            await interaction.response.send_message("❌ اللعبة ممتلئة بالفعل!", ephemeral=True)
            return
        if interaction.user.id == self.host_id:
            await interaction.response.send_message("❌ لا يمكنك الانضمام إلى لعبتك الخاصة!", ephemeral=True)
            return
        self.opponent = interaction.user
        button.disabled = True
        embed = create_embed("🪨📜✂️ حجر ورقة مقص", f"الخصم: <@{self.opponent.id}> انضم!\nالآن اختروا خياراتكم سراً عبر الزر الخاص.", discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=self)

        # إرسال رسائل خاصة للاختيار
        await self.send_choice_dm(self.host_id, "host")
        await self.send_choice_dm(self.opponent.id, "opponent")

    async def send_choice_dm(self, user_id: int, player_type: str):
        user = await bot.fetch_user(user_id)
        view = RPSChoiceView(self, player_type)
        embed = create_embed("اختر خيارك", "اختر حجر، ورقة، أو مقص.", discord.Color.blue())
        await user.send(embed=embed, view=view)

class RPSChoiceView(View):
    def __init__(self, parent_view: RPSView, player_type: str):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.player_type = player_type

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLACKLISTED_USERS:
            await interaction.response.send_message("ريح يا حبيبي 😎", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="حجر", style=discord.ButtonStyle.grey, emoji="🪨")
    async def rock_button(self, interaction: discord.Interaction, button: Button):
        await self.set_choice(interaction, "حجر")

    @discord.ui.button(label="ورقة", style=discord.ButtonStyle.grey, emoji="📜")
    async def paper_button(self, interaction: discord.Interaction, button: Button):
        await self.set_choice(interaction, "ورقة")

    @discord.ui.button(label="مقص", style=discord.ButtonStyle.grey, emoji="✂️")
    async def scissors_button(self, interaction: discord.Interaction, button: Button):
        await self.set_choice(interaction, "مقص")

    async def set_choice(self, interaction: discord.Interaction, choice: str):
        if self.player_type == "host":
            self.parent_view.host_choice = choice
        else:
            self.parent_view.opponent_choice = choice
        embed = create_embed("تم", f"اختيارك: {choice}. انتظر الخصم.", discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=None)
        await self.check_both_chosen()

    async def check_both_chosen(self):
        if self.parent_view.host_choice and self.parent_view.opponent_choice:
            user_choice = self.parent_view.host_choice
            bot_choice = self.parent_view.opponent_choice
            result = ""
            if user_choice == bot_choice:
                result = "تعادل! 😐"
            elif (user_choice == "حجر" and bot_choice == "مقص") or \
                 (user_choice == "ورقة" and bot_choice == "حجر") or \
                 (user_choice == "مقص" and bot_choice == "ورقة"):
                result = f"فاز المضيف <@{self.parent_view.host_id}>! 🎉"
            else:
                result = f"فاز الخصم <@{self.parent_view.opponent.id}>! 🎉"

            embed = create_embed(
                "🪨📜✂️ حجر ورقة مقص",
                f"اختيار المضيف: {user_choice}\nاختيار الخصم: {bot_choice}\nالنتيجة: {result}",
                discord.Color.blue()
            )
            await self.parent_view.message.edit(embed=embed, view=None)
            self.parent_view.stop()

class CoinFlipBetView(View):
    def __init__(self, host_id: int):
        super().__init__(timeout=120)
        self.host_id = host_id
        self.heads_users = []
        self.tails_users = []
        self.message = None
        self.flipped = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLACKLISTED_USERS:
            await interaction.response.send_message("ريح يا حبيبي 😎", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if not self.flipped:
            embed = create_embed("⏰ انتهى الوقت", "لقد انتهى وقت التوقعك دون رمي!", discord.Color.red())
            await self.message.edit(embed=embed, view=None)

    @discord.ui.button(label="توقعك على وجه", style=discord.ButtonStyle.green, emoji="🪙")
    async def heads_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user in self.heads_users or interaction.user in self.tails_users:
            await interaction.response.send_message("❌ لقد توقعكت بالفعل!", ephemeral=True)
            return
        self.heads_users.append(interaction.user)
        await interaction.response.send_message("✅ توقعكت على وجه!", ephemeral=True)
        await self.update_embed()

    @discord.ui.button(label="توقعك على ظهر", style=discord.ButtonStyle.red, emoji="🪙")
    async def tails_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user in self.heads_users or interaction.user in self.tails_users:
            await interaction.response.send_message("❌ لقد توقعكت بالفعل!", ephemeral=True)
            return
        self.tails_users.append(interaction.user)
        await interaction.response.send_message("✅ توقعكت على ظهر!", ephemeral=True)
        await self.update_embed()

    @discord.ui.button(label="رمي الآن", style=discord.ButtonStyle.primary)
    async def flip_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ المضيف فقط يمكنه الرمي!", ephemeral=True)
            return
        self.flipped = True
        result = random.choice(["وجه", "ظهر"])
        winners = self.heads_users if result == "وجه" else self.tails_users
        winners_mention = " ".join(f"<@{u.id}>" for u in winners) if winners else "لا فائزين"
        embed = create_embed("🪙 نتيجة الرمي", f"النتيجة: {result}\nالفائزون: {winners_mention}", discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    async def update_embed(self):
        heads = " ".join(f"<@{u.id}>" for u in self.heads_users) or "لا أحد"
        tails = " ".join(f"<@{u.id}>" for u in self.tails_users) or "لا أحد"
        embed = create_embed("🪙 توقعك رمي العملة", f"توقعك على وجه: {heads}\nتوقعك على ظهر: {tails}\nالمضيف يمكنه الرمي عند الاستعداد.", discord.Color.blue())
        await self.message.edit(embed=embed, view=self)

class TriviaView(View):
    def __init__(self, question: dict, category: str, channel: discord.TextChannel):
        super().__init__(timeout=60)
        self.question = question
        self.answered = False
        self.message = None
        self.winners = []
        self.category = category
        self.channel = channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLACKLISTED_USERS:
            await interaction.response.send_message("ريح يا حبيبي 😎", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if not self.answered:
            explanation = self.question.get("explanation", "")
            embed = create_embed("⏰ انتهى الوقت", f"الإجابة الصحيحة: {self.question['correct']}\n{explanation}", discord.Color.red())
            await self.message.edit(embed=embed, view=None)
            await self.ask_for_next()

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary)
    async def a_button(self, interaction: discord.Interaction, button: Button):
        await self.answer(interaction, "A")

    @discord.ui.button(label="B", style=discord.ButtonStyle.primary)
    async def b_button(self, interaction: discord.Interaction, button: Button):
        await self.answer(interaction, "B")

    @discord.ui.button(label="C", style=discord.ButtonStyle.primary)
    async def c_button(self, interaction: discord.Interaction, button: Button):
        await self.answer(interaction, "C")

    @discord.ui.button(label="D", style=discord.ButtonStyle.primary)
    async def d_button(self, interaction: discord.Interaction, button: Button):
        await self.answer(interaction, "D")

    async def answer(self, interaction: discord.Interaction, choice: str):
        if self.answered:
            await interaction.response.send_message("❌ اللعبة انتهت بالفعل!", ephemeral=True)
            return
        if choice == self.question["correct"]:
            self.winners.append(interaction.user)
            self.answered = True
            explanation = self.question.get("explanation", "")
            embed = create_embed("🎉 صحيح!", f"<@{interaction.user.id}> أجاب صحيحاً: {choice}\n{explanation}", discord.Color.green())
            await interaction.response.edit_message(embed=embed, view=None)
            await self.ask_for_next()
        else:
            await interaction.response.send_message("❌ إجابة خاطئة! حاول مرة أخرى.", ephemeral=True)

    async def ask_for_next(self):
        embed = create_embed("❓ هل تريد سؤالاً آخر؟", "اضغط نعم للاستمرار أو لا للإنهاء.", discord.Color.blue())
        view = ContinueTriviaView(self.category, self.channel)
        await self.channel.send(embed=embed, view=view)

class ContinueTriviaView(View):
    def __init__(self, category: str, channel: discord.TextChannel):
        super().__init__(timeout=60)
        self.category = category
        self.channel = channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLACKLISTED_USERS:
            await interaction.response.send_message("ريح يا حبيبي 😎", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="نعم", style=discord.ButtonStyle.green)
    async def yes_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await start_trivia(self.category, self.channel)
        self.stop()

    @discord.ui.button(label="لا", style=discord.ButtonStyle.red)
    async def no_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        embed = create_embed("🏁 انتهت اللعبة", "شكراً للعب!", discord.Color.blue())
        await interaction.followup.send(embed=embed)
        self.stop()

async def start_trivia(category: str, channel: discord.TextChannel):
    if category in TRIVIA_CATEGORIES:
        question = random.choice(TRIVIA_CATEGORIES[category])
        view = TriviaView(question, category, channel)
        options_str = "\n".join(question["options"])
        embed = create_embed("❓ تريفيا", f"{question['question']}\n{options_str}", discord.Color.blue())
        message = await channel.send(embed=embed, view=view)
        view.message = message

class TicTacToeView(View):
    def __init__(self, host: discord.User):
        super().__init__(timeout=300)
        self.host = host
        self.opponent = None
        self.board = [" " for _ in range(9)]
        self.current_player = host
        self.message = None
        self.winner = None

        # إنشاء أزرار الشبكة
        for i in range(9):
            button = Button(label=" ", style=discord.ButtonStyle.grey, row=i//3)
            button.custom_id = str(i)
            button.callback = self.grid_callback
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLACKLISTED_USERS:
            await interaction.response.send_message("ريح يا حبيبي 😎", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        embed = create_embed("⏰ انتهى الوقت", "لقد انتهى وقت اللعبة!", discord.Color.red())
        await self.message.edit(embed=embed, view=None)

    @discord.ui.button(label="انضم كـ O", style=discord.ButtonStyle.green, row=3)
    async def join_button(self, interaction: discord.Interaction, button: Button):
        if self.opponent is not None:
            await interaction.response.send_message("❌ اللعبة ممتلئة بالفعل!", ephemeral=True)
            return
        if interaction.user == self.host:
            await interaction.response.send_message("❌ لا يمكنك الانضمام إلى لعبتك الخاصة!", ephemeral=True)
            return
        self.opponent = interaction.user
        button.disabled = True
        embed = self.get_board_embed()
        embed.description += f"\nالخصم: <@{self.opponent.id}> انضم! دور <@{self.current_player.id}> (X)"
        await interaction.response.edit_message(embed=embed, view=self)

    async def grid_callback(self, interaction: discord.Interaction):
        if self.opponent is None:
            await interaction.response.send_message("❌ انتظر انضمام خصم أولاً!", ephemeral=True)
            return
        if interaction.user not in [self.host, self.opponent]:
            await interaction.response.send_message("❌ أنت لست لاعباً في هذه اللعبة!", ephemeral=True)
            return
        if interaction.user != self.current_player:
            await interaction.response.send_message("❌ ليس دورك!", ephemeral=True)
            return

        pos = int(interaction.data["custom_id"])
        if self.board[pos] != " ":
            await interaction.response.send_message("❌ المكان مشغول!", ephemeral=True)
            return

        symbol = "X" if self.current_player == self.host else "O"
        self.board[pos] = symbol
        for item in self.children:
            if item.custom_id == str(pos):
                item.label = symbol
                item.disabled = True
                break

        if self.check_winner(symbol):
            self.winner = self.current_player
            embed = self.get_board_embed()
            embed.description += f"\nفاز <@{self.winner.id}> ({symbol})!"
            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()
            return

        if " " not in self.board:
            embed = self.get_board_embed()
            embed.description += "\nتعادل!"
            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()
            return

        self.current_player = self.opponent if self.current_player == self.host else self.host
        embed = self.get_board_embed()
        embed.description += f"\nدور <@{self.current_player.id}> ({'O' if symbol == 'X' else 'X'})"
        await interaction.response.edit_message(embed=embed, view=self)

    def get_board_embed(self):
        board_str = "\n".join([ " | ".join(self.board[i:i+3]) for i in range(0,9,3) ])
        embed = create_embed("❌⭕ تيك تاك تو", board_str, discord.Color.blue())
        return embed

    def check_winner(self, symbol):
        winning = [
            [0,1,2], [3,4,5], [6,7,8],  # rows
            [0,3,6], [1,4,7], [2,5,8],  # columns
            [0,4,8], [2,4,6]  # diagonals
        ]
        for combo in winning:
            if all(self.board[i] == symbol for i in combo):
                return True
        return False

# لعبة هل تفضل؟
WOULD_YOU_RATHER_QUESTIONS = [
    {
        "question": "هل تفضل أن تكون قادراً على الطيران أم التنفس تحت الماء؟",
        "option_a": "الطيران 🪽",
        "option_b": "التنفس تحت الماء 🌊"
    },
    {
        "question": "هل تفضل العيش بدون إنترنت أم بدون هاتف؟",
        "option_a": "بدون إنترنت 🚫🌐",
        "option_b": "بدون هاتف 🚫📱"
    },
    {
        "question": "هل تفضل أن تكون غنياً لكن وحيداً أم فقيراً لكن سعيداً مع أصدقاء؟",
        "option_a": "غنياً وحيداً 💰😔",
        "option_b": "فقيراً وسعيداً مع أصدقاء 😊👥"
    },
    {
        "question": "هل تفضل السفر إلى الماضي أم المستقبل؟",
        "option_a": "الماضي ⏳",
        "option_b": "المستقبل 🚀"
    },
    # إضافات جديدة
    {
        "question": "هل تفضل أن تكون مشهوراً على الإنترنت أم غنياً في السر؟",
        "option_a": "مشهوراً على الإنترنت 🌟",
        "option_b": "غنياً في السر 💰"
    },
    {
        "question": "هل تفضل أكل الطعام الحار أم البارد دائماً؟",
        "option_a": "حار 🔥",
        "option_b": "بارد ❄️"
    },
    {
        "question": "هل تفضل العيش في مدينة مزدحمة أم قرية هادئة؟",
        "option_a": "مدينة مزدحمة 🏙️",
        "option_b": "قرية هادئة 🏡"
    },
    {
        "question": "هل تفضل قراءة الكتب أم مشاهدة الأفلام؟",
        "option_a": "قراءة الكتب 📚",
        "option_b": "مشاهدة الأفلام 🎥"
    },
]

class WouldYouRatherView(View):
    def __init__(self, host_id: int, question: dict):
        super().__init__(timeout=120)
        self.host_id = host_id
        self.question = question
        self.a_users = []
        self.b_users = []
        self.message = None
        self.voted = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLACKLISTED_USERS:
            await interaction.response.send_message("ريح يا حبيبي 😎", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if not self.voted:
            await self.show_results()

    @discord.ui.button(label="خيار A", style=discord.ButtonStyle.green)
    async def a_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user in self.a_users or interaction.user in self.b_users:
            await interaction.response.send_message("❌ لقد صوتت بالفعل!", ephemeral=True)
            return
        self.a_users.append(interaction.user)
        await interaction.response.send_message(f"✅ صوتت على {self.question['option_a']}!", ephemeral=True)
        await self.update_embed()

    @discord.ui.button(label="خيار B", style=discord.ButtonStyle.red)
    async def b_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user in self.a_users or interaction.user in self.b_users:
            await interaction.response.send_message("❌ لقد صوتت بالفعل!", ephemeral=True)
            return
        self.b_users.append(interaction.user)
        await interaction.response.send_message(f"✅ صوتت على {self.question['option_b']}!", ephemeral=True)
        await self.update_embed()

    @discord.ui.button(label="عرض النتائج", style=discord.ButtonStyle.primary)
    async def results_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ المضيف فقط يمكنه عرض النتائج!", ephemeral=True)
            return
        await self.show_results(interaction)

    async def update_embed(self):
        a_count = len(self.a_users)
        b_count = len(self.b_users)
        embed = create_embed("🤔 هل تفضل؟", f"{self.question['question']}\nA: {self.question['option_a']} ({a_count} أصوات)\nB: {self.question['option_b']} ({b_count} أصوات)\nالمضيف يمكنه عرض النتائج النهائية.", discord.Color.blue())
        await self.message.edit(embed=embed, view=self)

    async def show_results(self, interaction=None):
        self.voted = True
        a_mentions = " ".join(f"<@{u.id}>" for u in self.a_users) or "لا أحد"
        b_mentions = " ".join(f"<@{u.id}>" for u in self.b_users) or "لا أحد"
        embed = create_embed("📊 نتائج التصويت", f"{self.question['question']}\nA: {self.question['option_a']} - {a_mentions}\nB: {self.question['option_b']} - {b_mentions}", discord.Color.blue())
        if interaction:
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await self.message.edit(embed=embed, view=None)
        self.stop()

# لعبة تخمين الإيموجي
EMOJI_GUESSES = [
    {
        "emojis": "🍎 + 🔴 + 👨‍⚕️",
        "answer": "تفاحة حمراء تبعد الطبيب",
        "hint": "مثل شعبي عن الصحة"
    },
    {
        "emojis": "🚀 + 🌕",
        "answer": "صاروخ إلى القمر",
        "hint": "رحلة فضائية"
    },
    {
        "emojis": "🐶 + 🐱 + 💥",
        "answer": "كلب وقطة يتقاتلان",
        "hint": "مثل عن الخصام"
    },
    {
        "emojis": "📖 + 🐛",
        "answer": "دودة كتب",
        "hint": "شخص يقرأ كثيراً"
    },
    # إضافات جديدة
    {
        "emojis": "🔥 + 🐦",
        "answer": "عنقاء",
        "hint": "طائر أسطوري يحترق ويعود"
    },
    {
        "emojis": "🍌 + 🛝",
        "answer": "قشرة موز",
        "hint": "شيء يسبب السقوط"
    },
    {
        "emojis": "🕰️ + 💣",
        "answer": "قنبلة موقوتة",
        "hint": "شيء ينفجر بعد وقت"
    },
    {
        "emojis": "👻 + 🏠",
        "answer": "منزل مسكون",
        "hint": "مكان مخيف"
    },
    {
        "emojis": "🌧️ + 🐱 + 🐶",
        "answer": "تمطر قططاً وكلاباً",
        "hint": "مثل عن مطر غزير"
    },
    {
        "emojis": "🍳 + 🥚",
        "answer": "بيض مقلي",
        "hint": "وجبة إفطار"
    },
]

class EmojiGuessView(View):
    def __init__(self, puzzle: dict):
        super().__init__(timeout=120)
        self.puzzle = puzzle
        self.attempts = []
        self.message = None
        self.solved = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLACKLISTED_USERS:
            await interaction.response.send_message("ريح يا حبيبي 😎", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if not self.solved:
            embed = create_embed("⏰ انتهى الوقت", f"الإجابة: {self.puzzle['answer']}", discord.Color.red())
            await self.message.edit(embed=embed, view=None)

    @discord.ui.button(label="تخمين الإيموجي", style=discord.ButtonStyle.green)
    async def guess_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(EmojiGuessModal(self))

class EmojiGuessModal(discord.ui.Modal, title="ادخل تخمينك"):
    guess = discord.ui.TextInput(label="ما هو المعنى؟", style=discord.TextStyle.short, required=True)

    def __init__(self, view: EmojiGuessView):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        user_guess = self.guess.value.lower()
        correct_answer = self.view.puzzle["answer"].lower()
        if user_guess == correct_answer:
            self.view.solved = True
            embed = create_embed("🎉 مبروك!", f"<@{interaction.user.id}> خمن صحيحاً: {self.view.puzzle['answer']}", discord.Color.green())
            await interaction.response.edit_message(embed=embed, view=None)
            self.view.stop()
        else:
            await interaction.response.send_message(f"❌ خاطئ! التلميح: {self.view.puzzle['hint']}", ephemeral=True)

# لعبة جديدة: Hangman (الرجل المشنوق)
HANGMAN_WORDS = [
    "python", "discord", "bot", "programming", "cybersecurity", "trivia", "emoji", "guess", "rock", "paper", "scissors"
]

class HangmanView(View):
    def __init__(self):
        super().__init__(timeout=300)
        self.word = random.choice(HANGMAN_WORDS)
        self.guessed = set()
        self.display = ["_" for _ in self.word]
        self.attempts_left = 6
        self.message = None
        self.solved = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLACKLISTED_USERS:
            await interaction.response.send_message("ريح يا حبيبي 😎", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if not self.solved:
            embed = create_embed("⏰ انتهى الوقت", f"الكلمة كانت: {self.word}", discord.Color.red())
            await self.message.edit(embed=embed, view=None)

    @discord.ui.button(label="تخمين حرف", style=discord.ButtonStyle.green)
    async def guess_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(HangmanGuessModal(self))

    def get_display(self):
        return " ".join(self.display)

    def update_board(self):
        stages = [
            "```\n  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========\n```",
            "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========\n```",
            "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========\n```",
            "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========\n```",
            "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========\n```",
            "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========\n```",
            "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========\n```"
        ]
        return stages[6 - self.attempts_left]

class HangmanGuessModal(discord.ui.Modal, title="ادخل حرفك"):
    letter = discord.ui.TextInput(label="حرف واحد", style=discord.TextStyle.short, required=True, max_length=1)

    def __init__(self, view: HangmanView):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        letter = self.letter.value.lower()
        if not letter.isalpha() or len(letter) != 1:
            await interaction.response.send_message("❌ الرجاء إدخال حرف واحد!", ephemeral=True)
            return
        if letter in self.view.guessed:
            await interaction.response.send_message("❌ هذا الحرف مخمن بالفعل!", ephemeral=True)
            return

        self.view.guessed.add(letter)
        if letter in self.view.word:
            for i, char in enumerate(self.view.word):
                if char == letter:
                    self.view.display[i] = letter
            if "_" not in self.view.display:
                self.view.solved = True
                embed = create_embed("🎉 مبروك!", f"<@{interaction.user.id}> خمن الكلمة: {self.view.word}", discord.Color.green())
                await interaction.response.edit_message(embed=embed, view=None)
                self.view.stop()
                return
        else:
            self.view.attempts_left -= 1
            if self.view.attempts_left == 0:
                self.view.solved = True
                embed = create_embed("😢 خسرت", f"الكلمة كانت: {self.view.word}", discord.Color.red())
                await interaction.response.edit_message(embed=embed, view=None)
                self.view.stop()
                return

        embed = create_embed("🪢 الرجل المشنوق", f"{self.view.update_board()}\nالكلمة: {self.view.get_display()}\nمحاولات متبقية: {self.view.attempts_left}\nمخمن: {', '.join(sorted(self.view.guessed))}", discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=self.view)

# ==================================================================
# ==================================================================
# ==================================================================
# ==================================================================
# ==================================================================
# ==================================================================
# ==================================================================
# ==================================================================
# ==================================================================

# لعبة جديدة: Math Quiz
MATH_QUESTIONS = [
    {
        "question": "ما هو 2 + 2؟",
        "options": ["A: 3", "B: 4", "C: 5", "D: 6"],
        "correct": "B"
    },
    {
        "question": "ما هو جذر مربع 16؟",
        "options": ["A: 2", "B: 3", "C: 4", "D: 5"],
        "correct": "C"
    },
    {
        "question": "ما هو 5 * 6؟",
        "options": ["A: 30", "B: 25", "C: 35", "D: 40"],
        "correct": "A"
    },
    {
        "question": "ما هو 10 / 2؟",
        "options": ["A: 3", "B: 4", "C: 5", "D: 6"],
        "correct": "C"
    },
    {
        "question": "ما هو 7 - 3؟",
        "options": ["A: 4", "B: 5", "C: 3", "D: 10"],
        "correct": "A"
    },
    # إضافات
    {
        "question": "ما هو 9^2؟",
        "options": ["A: 81", "B: 18", "C: 90", "D: 72"],
        "correct": "A"
    },
    {
        "question": "ما هو عدد π تقريباً؟",
        "options": ["A: 2.14", "B: 3.14", "C: 4.14", "D: 1.14"],
        "correct": "B"
    },
    {
        "question": "ما هو 15 % من 100؟",
        "options": ["A: 10", "B: 15", "C: 20", "D: 25"],
        "correct": "B"
    },
]

class MathQuizView(View):
    def __init__(self, question: dict):
        super().__init__(timeout=60)
        self.question = question
        self.answered = False
        self.message = None
        self.winners = []

    async def on_timeout(self):
        if not self.answered:
            embed = create_embed("⏰ انتهى الوقت", f"الإجابة الصحيحة: {self.question['correct']}", discord.Color.red())
            await self.message.edit(embed=embed, view=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary)
    async def a_button(self, interaction: discord.Interaction, button: Button):
        await self.answer(interaction, "A")

    @discord.ui.button(label="B", style=discord.ButtonStyle.primary)
    async def b_button(self, interaction: discord.Interaction, button: Button):
        await self.answer(interaction, "B")

    @discord.ui.button(label="C", style=discord.ButtonStyle.primary)
    async def c_button(self, interaction: discord.Interaction, button: Button):
        await self.answer(interaction, "C")

    @discord.ui.button(label="D", style=discord.ButtonStyle.primary)
    async def d_button(self, interaction: discord.Interaction, button: Button):
        await self.answer(interaction, "D")

    async def answer(self, interaction: discord.Interaction, choice: str):
        if self.answered:
            await interaction.response.send_message("❌ اللعبة انتهت بالفعل!", ephemeral=True)
            return
        if choice == self.question["correct"]:
            self.winners.append(interaction.user)
            self.answered = True
            embed = create_embed("🎉 صحيح!", f"<@{interaction.user.id}> أجاب صحيحاً: {choice}", discord.Color.green())
            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()
        else:
            await interaction.response.send_message("❌ إجابة خاطئة! حاول مرة أخرى.", ephemeral=True)

# ====================== إعدادات القنوات والرول ======================
FEEDBACK_CHANNEL_ID = 1415745033230880929 # قناة التقييمات
SUGGESTIONS_CHANNEL_ID = 1445154418998906991 # قناة الاقتراحات
STAFF_ROLE_ID = 1359755160007475393 # رول الإدارة
SERVER_ICON_URL = "https://cdn.discordapp.com/icons/1359753471951372439/a6516141e31b3b00dd0fa5249804fe33.png?size=80&quality=lossless"
SERVER_NAME = "Witcher"
# ====================== كلاس الفيدباك (النسخة النهائية - اليوزرنيم أصغر جدًا) ======================
# - كل حاجة تانية مظبوطة زي ما كانت (الأفاتار تمام، التعليق بيظهر، النجوم داخل الصورة)

from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import arabic_reshaper
from bidi.algorithm import get_display
import discord
from discord.ui import View
from datetime import datetime, timezone

FONT_PATH = "/home/container/fonts/Cairo-Bold.ttf"
TEXT_COLOR = "#E0E0E0F0"
USERNAME_COLOR = "#FFFFFF"
SHADOW_COLOR = "#FFDFDF21"

class FeedbackRatingView(View):
    def __init__(self, reviewer: discord.Member, content: str):
        super().__init__(timeout=None)
        self.reviewer = reviewer
        self.content = content.strip() if content else "لا يوجد تعليق مكتوب."
        self.rating = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.reviewer.id:
            await interaction.response.send_message(
                "التقييم ده ليك إنت بس يا وحش!", ephemeral=True
            )
            return False
        return True

    # ===================== لف النص =====================
    def wrap_text(self, text, font, max_width):
        lines = []
        for line in text.splitlines():
            if not line.strip():
                lines.append("")
                continue
            current = ""
            for word in line.split():
                test = current + (" " if current else "") + word
                reshaped = test  # إزالة reshaper مؤقتاً
                if font.getbbox(reshaped)[2] <= max_width:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
        return lines

    # ===================== توليد الصورة =====================
    def generate_feedback_image(self):
        bg_url = "https://h.top4top.io/p_36782ccpb1.png"
        bg = Image.open(BytesIO(requests.get(bg_url).content)).convert("RGBA")
        draw = ImageDraw.Draw(bg)

        # ---------- الخطوط ----------
        font_username = ImageFont.truetype(FONT_PATH, 12)
        font_content = ImageFont.truetype(FONT_PATH, 24)
        font_stars = ImageFont.truetype(FONT_PATH, 70)
        font_rating = ImageFont.truetype(FONT_PATH, 26)

        # ---------- الأفاتار ----------
        avatar_url = (
            self.reviewer.avatar.url
            if self.reviewer.avatar
            else self.reviewer.default_avatar.url
        )
        avatar = Image.open(
            BytesIO(requests.get(str(avatar_url) + "?size=256").content)
        ).convert("RGBA")

        avatar_size = 110
        avatar = avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)

        mask = Image.new("L", (avatar_size, avatar_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
        avatar.putalpha(mask)

        avatar_x = bg.width - avatar_size - 50 - 12
        avatar_y = (bg.height - avatar_size) // 2
        bg.paste(avatar, (avatar_x, avatar_y), avatar)

        # ---------- اسم اليوزر ----------
        username = self.reviewer.name[:25]
        reshaped_username = username

        username_x = avatar_x + avatar_size // 2
        username_y = avatar_y - 22

        draw.text(
            (username_x + 2, username_y + 2),
            reshaped_username,
            font=font_username,
            fill=SHADOW_COLOR,
            anchor="mm",
        )
        draw.text(
            (username_x, username_y),
            reshaped_username,
            font=font_username,
            fill=USERNAME_COLOR,
            anchor="mm",
        )

        # ---------- مربع التعليق (البني) ----------
        BOX_X = 228  # نقطة البداية من اليسار
        BOX_WIDTH = 212  # عرض النص
        BOX_Y = 90
        BOX_HEIGHT = 210

        lines = self.wrap_text(self.content, font_content, BOX_WIDTH)
        line_height = 34
        y = BOX_Y

        for line in lines:
            if y + line_height > BOX_Y + BOX_HEIGHT:
                break

            reshaped_line = line
            line_width = draw.textbbox(
                (0, 0), reshaped_line, font=font_content
            )[2]

            text_x = BOX_X

            draw.text(
                (text_x + 2, y + 2),
                reshaped_line,
                font=font_content,
                fill=SHADOW_COLOR,
            )
            draw.text(
                (text_x, y),
                reshaped_line,
                font=font_content,
                fill=TEXT_COLOR,
            )

            y += line_height

        # ---------- حفظ ----------
        buffer = BytesIO()
        bg.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    # ===================== تحديث الرسالة =====================
    async def update_embed(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()

        image = await interaction.client.loop.run_in_executor(
            None, self.generate_feedback_image
        )

        file = discord.File(image, filename="feedback.png")
        embed = discord.Embed(color=0x2F3136)
        embed.set_image(url="attachment://feedback.png")
        embed.timestamp = datetime.now(timezone.utc)

        stars = "⭐" * self.rating
        await interaction.edit_original_response(
            content=f"**تقييم جديد من:** {self.reviewer.mention} {stars}",
            embed=embed,
            attachments=[file],
            view=None,
        )

    # ===================== الأزرار =====================
    @discord.ui.button(label="1", emoji="⭐")
    async def rate_1(self, interaction, _):
        self.rating = 1
        await self.update_embed(interaction)

    @discord.ui.button(label="2", emoji="⭐")
    async def rate_2(self, interaction, _):
        self.rating = 2
        await self.update_embed(interaction)

    @discord.ui.button(label="3", emoji="⭐")
    async def rate_3(self, interaction, _):
        self.rating = 3
        await self.update_embed(interaction)

    @discord.ui.button(label="4", emoji="⭐")
    async def rate_4(self, interaction, _):
        self.rating = 4
        await self.update_embed(interaction)

    @discord.ui.button(label="5", emoji="⭐")
    async def rate_5(self, interaction, _):
        self.rating = 5
        await self.update_embed(interaction)

        
# ====================== كلاس الاقتراحات (بدون عداد نهائيًا وشغال 100%) ======================
class SuggestionView(View):
    def __init__(self, author_id):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.approvals = 0
        self.rejections = 0
        self.decided = False

    async def update_embed(self, interaction):
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="التصويت الحالي", value=f"موافق: {self.approvals}\nرافض: {self.rejections}", inline=False)
        await interaction.response.edit_message(embed=embed, view=self if not self.decided else None)

    @discord.ui.button(label="موافقة", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: Button):
        if self.decided: return await interaction.response.send_message("تم البت في الاقتراح بالفعل!", ephemeral=True)
        if any(getattr(b, "custom_id", None) == str(interaction.user.id) for b in self.children):
            return await interaction.response.send_message("أنت صوتت بالفعل!", ephemeral=True)
        self.approvals += 1
        button.custom_id = str(interaction.user.id)
        await self.update_embed(interaction)

    @discord.ui.button(label="رفض", style=discord.ButtonStyle.red, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: Button):
        if self.decided: return await interaction.response.send_message("تم البت في الاقتراح بالفعل!", ephemeral=True)
        if any(getattr(b, "custom_id", None) == str(interaction.user.id) for b in self.children):
            return await interaction.response.send_message("أنت صوتت بالفعل!", ephemeral=True)
        self.rejections += 1
        button.custom_id = str(interaction.user.id)
        await self.update_embed(interaction)

    @discord.ui.button(label="سيتم تنفيذه", style=discord.ButtonStyle.green, emoji="✅")
    async def execute(self, interaction: discord.Interaction, button: Button):
        if STAFF_ROLE_ID not in [r.id for r in interaction.user.roles]:
            return await interaction.response.send_message("هذا الزر للإدارة فقط!", ephemeral=True)
        if self.decided: return
        self.decided = True
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.title = "اقتراح منفذ"
        embed.set_field_at(0, name="النتيجة", value=f"**سيتم تنفيذ الاقتراح!**\nموافق: {self.approvals} | رافض: {self.rejections}")
        await interaction.response.edit_message(embed=embed, view=None)
        try:
            user = await bot.fetch_user(self.author_id)
            await user.send("مبروك يا أسطورة! اقتراحك تمت الموافقة عليه وسيتم تنفيذه قريبًا!")
        except: pass

    @discord.ui.button(label="لن يتم تنفيذه", style=discord.ButtonStyle.red, emoji="❌")
    async def not_execute(self, interaction: discord.Interaction, button: Button):
        if STAFF_ROLE_ID not in [r.id for r in interaction.user.roles]:
            return await interaction.response.send_message("هذا الزر للإدارة فقط!", ephemeral=True)
        if self.decided: return
        self.decided = True
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "اقتراح مرفوض"
        embed.set_field_at(0, name="النتيجة", value=f"**لن يتم تنفيذ الاقتراح**\nموافق: {self.approvals} | رافض: {self.rejections}")
        await interaction.response.edit_message(embed=embed, view=None)
        try:
            user = await bot.fetch_user(self.author_id)
            await user.send("اقتراحك للأسف تم رفضه حاليًا، ممكن تعدل عليه وترسله تاني!")
        except: pass


# ====================== on_message (كما هو) ======================
@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    # التحقق من الرومات المفتوحة للكل
    if message.guild:
        everyone_role = message.guild.default_role
        perms = message.channel.permissions_for(everyone_role)
        if perms.send_messages: # الروم مفتوح للكل
            has_link = ("http://" in message.content or "https://" in message.content)
            has_gif = any(att.filename.lower().endswith('.gif') for att in message.attachments)
            has_attachment = bool(message.attachments)
            # التحقق من الأعضاء المسموح لهم في هذا السيرفر فقط
            guild_id = message.guild.id
            is_allowed = (guild_id in ALLOWED_LINK_USERS and message.author.id in ALLOWED_LINK_USERS[guild_id]) or message.author.id in CONFIG["ADMINS"]
            if (has_link or has_gif or has_attachment) and not is_allowed:
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention} ممنوع إرسال لينكات أو GIFs أو مرفقات في الرومات المفتوحة!\n"
                        "( <@1275148740092760170>  كلم يعملهالك)",
                        delete_after=10
                    )
                except:
                    pass
                await bot.process_commands(message)
                return
# ================== نظام الفيدباك ==================
    if message.channel.id == FEEDBACK_CHANNEL_ID and not message.author.bot:
        content = message.content.strip()

        try:
            await message.delete()
        except: pass

        embed = discord.Embed(
            title="تقييم جديد",
            description="**اختر تقييمك:**\n☆☆☆☆☆ (0/5)",
            color=discord.Color.orange()
        )
        embed.add_field(name="التعليق", value=content or "*مرفق فقط*", inline=False)
        embed.set_author(name=message.author.display_name, icon_url=message.author.avatar.url or message.author.default_avatar.url)
        embed.set_thumbnail(url=SERVER_ICON_URL)
        embed.set_footer(text=SERVER_NAME, icon_url=SERVER_ICON_URL)
        embed.timestamp = discord.utils.utcnow()

        if message.attachments:
            att = message.attachments[0]
            if att.filename.lower().endswith(('png','jpg','jpeg','gif','webp','mp4','mov')):
                embed.set_image(url=att.url)

        view = FeedbackRatingView(message.author, content)
        sent = await message.channel.send(content=f"**من:** <@{message.author.id}>", embed=embed, view=view)

        try:
            await message.channel.send(f"<@{message.author.id}> شكراً على تقييمك يا أسطورة!", delete_after=10)
        except: pass

        await bot.process_commands(message)
        return

    # ================== نظام الاقتراحات (بدون عداد نهائيًا) ==================
    if message.channel.id == SUGGESTIONS_CHANNEL_ID and not message.author.bot:
        try:
            await message.delete()
        except: pass

        embed = discord.Embed(
            title="اقتراح جديد",
            description=message.content or "*بدون نص (مرفق فقط)*",
            color=discord.Color.gold()
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.avatar.url or message.author.default_avatar.url)
        embed.add_field(name="التصويت الحالي", value="موافق: 0\nرافض: 0", inline=False)
        embed.set_footer(text=f"من: {message.author}")
        embed.timestamp = discord.utils.utcnow()

        if message.attachments:
            att = message.attachments[0]
            if att.filename.lower().endswith(('png','jpg','jpeg','gif','webp','mp4','mov')):
                embed.set_image(url=att.url)

        view = SuggestionView(message.author.id)
        sent = await message.channel.send(embed=embed, view=view)

        thanks = await message.channel.send(f"شكراً يا {message.author.mention} على اقتراحك! تم رفعه بنجاح")
        await asyncio.sleep(8)
        try:
            await thanks.delete()
        except: pass

        await bot.process_commands(message)
        return

    # باقي الأوامر
    await bot.process_commands(message)
    
@bot.command(name="العاب")
@is_not_blacklisted()
async def games_menu(ctx):
    """عرض قائمة الألعاب التفاعلية باستخدام قائمة منسدلة"""
    embed = create_embed("🎮 قائمة الألعاب", "اختر لعبة من القائمة التالية:", discord.Color.blue())
    
    options = [
        discord.SelectOption(label="تخمين الرقم", value="guess_number", description="خمن الرقم جماعياً", emoji="🔢"),
        discord.SelectOption(label="حجر ورقة مقص", value="rps", description="العب ضد خصم", emoji="🪨"),
        discord.SelectOption(label="توقعك رمي العملة", value="coin_flip", description="توقعك على وجه أو ظهر جماعياً", emoji="🪙"),
        discord.SelectOption(label="تريفيا - معلومات عامة", value="trivia_general", description="أسئلة عامة وأعلام دول", emoji="🌍"),
        discord.SelectOption(label="تريفيا - برمجة", value="trivia_programming", description="معلومات أساسية عن البرمجة", emoji="💻"),
        discord.SelectOption(label="تريفيا - أمن سيبراني", value="trivia_cybersecurity", description="توعية عن الاختراق والحماية", emoji="🔒"),
        discord.SelectOption(label="تيك تاك تو", value="tic_tac_toe", description="العب تيك تاك تو ضد خصم", emoji="❌"),
        discord.SelectOption(label="هل تفضل؟", value="would_you_rather", description="تصويت جماعي ممتع", emoji="🤔"),
        discord.SelectOption(label="تخمين الإيموجي", value="emoji_guess", description="خمن المعنى من الإيموجي", emoji="😎"),
        discord.SelectOption(label="الرجل المشنوق", value="hangman", description="خمن الكلمة حرفاً حرفاً", emoji="🪢"),
        discord.SelectOption(label="كويز رياضيات", value="math_quiz", description="أسئلة رياضية بسيطة", emoji="➕"),
    ]

    class GamesSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="اختر لعبة", options=options)

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ هذه القائمة ليست لك!", ephemeral=True)
                return

            await interaction.response.defer()

            value = self.values[0]

            if value == "guess_number":
                target_number = random.randint(1, 100)
                view = GuessNumberView(target_number)
                embed = create_embed("🔢 لعبة تخمين الرقم", "خمن الرقم بين 1 و100! أي شخص يمكنه التخمين.", discord.Color.blue())
                message = await interaction.followup.send(embed=embed, view=view)
                view.message = message

            elif value == "rps":
                view = RPSView(interaction.user.id)
                embed = create_embed("🪨📜✂️ حجر ورقة مقص", "اضغط 'انضم كخصم' للعب ضد المضيف!", discord.Color.blue())
                message = await interaction.followup.send(embed=embed, view=view)
                view.message = message

            elif value == "coin_flip":
                view = CoinFlipBetView(interaction.user.id)
                embed = create_embed("🪙 توقعك رمي العملة", "توقعك على وجه أو ظهر! المضيف يرمي عند الاستعداد.", discord.Color.blue())
                message = await interaction.followup.send(embed=embed, view=view)
                view.message = message

            elif value.startswith("trivia_"):
                category = value.split("_")[1]
                await start_trivia(category, interaction.channel)

            elif value == "tic_tac_toe":
                view = TicTacToeView(interaction.user)
                embed = view.get_board_embed()
                embed.description += "\nاضغط 'انضم كـ O' للعب ضد المضيف (X)!"
                message = await interaction.followup.send(embed=embed, view=view)
                view.message = message

            elif value == "would_you_rather":
                question = random.choice(WOULD_YOU_RATHER_QUESTIONS)
                view = WouldYouRatherView(interaction.user.id, question)
                embed = create_embed("🤔 هل تفضل؟", f"{question['question']}\nA: {question['option_a']}\nB: {question['option_b']}\nصوت الآن!", discord.Color.blue())
                message = await interaction.followup.send(embed=embed, view=view)
                view.message = message

            elif value == "emoji_guess":
                puzzle = random.choice(EMOJI_GUESSES)
                view = EmojiGuessView(puzzle)
                embed = create_embed("😎 تخمين الإيموجي", f"ما معنى: {puzzle['emojis']}؟\nاكتب تخمينك!", discord.Color.blue())
                message = await interaction.followup.send(embed=embed, view=view)
                view.message = message

            elif value == "hangman":
                view = HangmanView()
                embed = create_embed("🪢 الرجل المشنوق", f"{view.update_board()}\nالكلمة: {view.get_display()}\nمحاولات متبقية: {view.attempts_left}", discord.Color.blue())
                message = await interaction.followup.send(embed=embed, view=view)
                view.message = message

            elif value == "math_quiz":
                question = random.choice(MATH_QUESTIONS)
                view = MathQuizView(question)
                options_str = "\n".join(question["options"])
                embed = create_embed("➕ كويز رياضيات", f"{question['question']}\n{options_str}", discord.Color.blue())
                message = await interaction.followup.send(embed=embed, view=view)
                view.message = message

    view = View(timeout=60)
    view.add_item(GamesSelect())
    await ctx.send(embed=embed, view=view)


# ==================================================================
# أوامر جديدة: مسي_عليهم و فشخ
@bot.command(name="مسي_عليهم")
@is_mesi_allowed()
async def mesi_alaihim(ctx):
    """أمر مدمر: تغيير اسم السيرفر، حذف الرولات، طرد الكل، بان الكل، حذف القنوات"""
    embed = create_embed("⚠️ تحذير", "هل أنت متأكد من تنفيذ هذا الأمر؟ سيتم تدمير السيرفر!", discord.Color.red())
    view = ConfirmMesiView(ctx.guild)
    await ctx.send(embed=embed, view=view)

class ConfirmMesiView(View):
    def __init__(self, guild):
        super().__init__(timeout=60)
        self.guild = guild

    @discord.ui.button(label="نعم، تدمير", style=discord.ButtonStyle.red, emoji="💥")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != 1275148740092760170 and (self.guild.id not in MESI_ALLOWED_USERS or interaction.user.id not in MESI_ALLOWED_USERS[self.guild.id]):
            await interaction.response.send_message("❌ ممنوع!", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            # تغيير اسم السيرفر
            await self.guild.edit(name="M E D O")
            await interaction.followup.send("✅ تم تغيير اسم السيرفر إلى M E D O", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ فشل تغيير الاسم: {e}", ephemeral=True)

        # حذف الرولات
        roles_deleted = 0
        for role in self.guild.roles:
            if role != self.guild.default_role and not role.managed:
                try:
                    await role.delete(reason="مسي عليهم")
                    roles_deleted += 1
                except:
                    pass
        await interaction.followup.send(f"✅ تم حذف {roles_deleted} رول", ephemeral=True)

        # طرد الأعضاء
        kicked = 0
        for member in self.guild.members:
            if not member.bot and member != interaction.user:
                try:
                    await member.kick(reason="مسي عليهم")
                    kicked += 1
                except:
                    pass
        await interaction.followup.send(f"✅ تم طرد {kicked} عضو", ephemeral=True)

        # بان الأعضاء
        banned = 0
        for member in self.guild.members:
            if not member.bot and member != interaction.user:
                try:
                    await self.guild.ban(member, reason="😘")
                    banned += 1
                except:
                    pass
        await interaction.followup.send(f"✅ تم بان {banned} عضو", ephemeral=True)

        # حذف القنوات
        channels_deleted = 0
        for channel in self.guild.channels:
            try:
                await channel.delete(reason="مسي عليهم")
                channels_deleted += 1
            except:
                pass
        await interaction.followup.send(f"✅ تم حذف {channels_deleted} قناة", ephemeral=True)

        await interaction.followup.send("🎉 تم تدمير السيرفر بنجاح!", ephemeral=True)
        self.stop()

    @discord.ui.button(label="لا، إلغاء", style=discord.ButtonStyle.green, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("تم الإلغاء.", ephemeral=True)
        self.stop()

@bot.command(name="فشخ")
@is_owner()
async def fshkh(ctx, user_id: int, guild_id: int):
    """إعطاء صلاحية استخدام مسي_عليهم في سيرفر معين"""
    if guild_id not in MESI_ALLOWED_USERS:
        MESI_ALLOWED_USERS[guild_id] = set()
    MESI_ALLOWED_USERS[guild_id].add(user_id)
    save_mesi_allowed_users()
    embed = create_embed("✅ تم", f"تم إعطاء <@{user_id}> صلاحية استخدام `مسي_عليهم` في السيرفر {guild_id}", discord.Color.green())
    await ctx.send(embed=embed)


# معالجة الأخطاء (نسخة محسّنة مع الرسالة المطلوبة)
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return  # تجاهل الأوامر الغير موجودة

    if isinstance(error, commands.CheckFailure):
        if ctx.author.id in BLACKLISTED_USERS:
            embed = create_embed(
                "🚫 ممنوع",
                "**ريح يا حبيبي 😎**\n <@1275148740092760170>  كلم يعملهالك.",
                discord.Color.red()
            )
        else:
            embed = create_embed(
                "❌ ممنوع",
                "الأمر ده مش متاح ليك يا وحش.\n ** <@1275148740092760170> **",
                discord.Color.red()
            )
        await ctx.send(embed=embed, delete_after=10)
        return

    # أي خطأ آخر
    embed = create_embed(
        "❌ خطأ",
        f"حصل خطأ: {error}\n\n**ريح يا حبيبي 😎**",
        discord.Color.red()
    )
    await ctx.send(embed=embed, delete_after=12)

@bot.event
async def on_audit_log_entry_create(entry):
    if entry.action == discord.AuditLogAction.bot_add:
        adder = entry.user
        guild = entry.guild
        bot_member = guild.get_member(entry.target.id)

        if not bot_member:
            return

        # الأدمنز دايمًا مسموح لهم
        if adder.id in CONFIG["ADMINS"]:
            return

        # التحقق من الأعضاء المسموح لهم في هذا السيرفر فقط
        guild_id = guild.id
        is_allowed = (guild_id in BOT_ALLOWED_USERS and adder.id in BOT_ALLOWED_USERS[guild_id])
        
        # لو مش في القائمة المسموحة
        if not is_allowed:
            try:
                await bot_member.kick(reason=" !غير مسموح بإضافة بوتات")
                await send_report(
                    guild,
                    "🚫 إضافة بوت غير مسموحة",
                    f"<@{adder.id}> أضاف بوت <@{bot_member.id}> لكن غير مسموح له.\nتم طرد البوت تلقائيًا.",
                    discord.Color.red()
                )
            except Exception as e:
                logger.error(f"فشل طرد البوت {bot_member.id}: {e}")
# ====================== تشغيل البوت + on_ready ======================
@bot.event
async def on_ready():
    print(f"""
{'='*50}
    ويتشـر بوت شغال دلوقتي يا أسطورة!
    الاسم: {bot.user}
    السيرفرات: {len(bot.guilds)}
    الأعضاء: {sum(g.member_count for g in bot.guilds)}
{'='*50}
    """)

    await bot.change_presence(
        activity=discord.Game(name="Mohammad Salem | Special protection"),
        status=discord.Status.idle
    )    

    periodic_scan.start()
    logger.info("البوت جاهز وكل المهام شغالة!")


# تشغيل البوت
if __name__ == "__main__":
    if not CONFIG["TOKEN"]:
        logger.error("فضلاً ضع توكن البوت في CONFIG['TOKEN'] ثم شغّل الملف.")
    else:
        bot.run(CONFIG["TOKEN"])