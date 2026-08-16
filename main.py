import asyncio,json,logging,os,time
from aiogram import Bot,Dispatcher,Router,F
from aiogram.filters import Command,CommandStart
from aiogram.types import Message,CallbackQuery,InlineKeyboardButton,InlineKeyboardMarkup
from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramRetryAfter
from config import *
from database.settings import Database,default_settings
from utils.formatter import format_caption

logging.basicConfig(level=logging.INFO,format='%(asctime)s | %(levelname)s | %(message)s'); log=logging.getLogger('caption-bot')
router=Router(); db=Database(); states={}; started=time.time(); runtime={'processed':0,'edited':0,'failed':0}

async def admin(uid): return await db.is_admin(uid)
async def fsub_ok(bot,uid):
    if not FSUB_CHANNEL:return True
    try:
        m=await bot.get_chat_member(FSUB_CHANNEL,uid)
        return m.status in ('creator','administrator','member')
    except Exception:return False
async def public_access(m):
    await db.user_upsert(m.from_user.id,m.from_user.username or '')
    if await admin(m.from_user.id):return True
    if not PUBLIC_MODE:
        await m.answer(f'🔒 This Bot Is Private\n\nPlease contact the administrator. {ADMIN_USERNAME}'); return False
    if not await fsub_ok(m.bot,m.from_user.id):
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📢 Join Channel',url=FSUB_CHANNEL,style=ButtonStyle.SUCCESS)]])
        text='🔒 <b>Join Required</b>\n\nPlease join our channel to use this bot.'
        if FSUB_PIC and os.path.exists(FSUB_PIC):
            with open(FSUB_PIC,'rb') as p: await m.answer_photo(p,caption=text,reply_markup=kb,parse_mode='HTML')
        else: await m.answer(text,reply_markup=kb,parse_mode='HTML')
        return False
    return True
async def admin_only(m):
    if await admin(m.from_user.id):return True
    if not PUBLIC_MODE: await m.answer(f'🔒 This Bot Is Private\n\nPlease contact the administrator. {ADMIN_USERNAME}')
    else: await m.answer('❌ Admin only.')
    return False

def cfg(row):
    base=default_settings()
    try: base.update(json.loads(row.get('config') or '{}'))
    except Exception: pass
    return base

def style(c): return {'blue':ButtonStyle.PRIMARY,'primary':ButtonStyle.PRIMARY,'green':ButtonStyle.SUCCESS,'success':ButtonStyle.SUCCESS,'red':ButtonStyle.DANGER,'danger':ButtonStyle.DANGER}.get(str(c).lower(),ButtonStyle.PRIMARY)
def menu(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📺 Channels',callback_data='channels',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text='📊 Stats',callback_data='stats',style=ButtonStyle.SUCCESS)],[InlineKeyboardButton(text='⚙️ Settings',callback_data='settings',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text='ℹ️ Help',callback_data='help',style=ButtonStyle.PRIMARY)]])
def channel_menu(rows):
    kb=[[InlineKeyboardButton(text=f'📢 {r.get("title","Channel")}',callback_data=f'ch:{r["channel_id"]}',style=ButtonStyle.PRIMARY)] for r in rows[:40]]
    kb += [[InlineKeyboardButton(text='➕ Add New Channel',callback_data='add_channel',style=ButtonStyle.SUCCESS)],[InlineKeyboardButton(text='↩️ Back',callback_data='home',style=ButtonStyle.PRIMARY)]]
    return InlineKeyboardMarkup(inline_keyboard=kb)
def settings_menu(cid,c):
    def s(x):return 'ON ✅' if x else 'OFF ❌'
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📝 Caption',callback_data=f'set:caption:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text=f'🔘 Buttons ({len(c["buttons"])})',callback_data=f'set:buttons:{cid}',style=ButtonStyle.SUCCESS)],[InlineKeyboardButton(text=f'🔄 Replace ({len(c["replacements"])})',callback_data=f'set:replace:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text=f'🎯 Filters {s(bool(c["filters"]))}',callback_data=f'set:filters:{cid}',style=ButtonStyle.SUCCESS)],[InlineKeyboardButton(text=f'📤 Forward {s(c["forward"]["enabled"])}',callback_data=f'set:forward:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text=f'✨ Prefix {s(bool(c["prefix"]))}',callback_data=f'set:prefix:{cid}',style=ButtonStyle.SUCCESS)],[InlineKeyboardButton(text=f'✨ Suffix {s(bool(c["suffix"]))}',callback_data=f'set:suffix:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text=f'🎉 Stickers {s(c["stickers"]["enabled"])}',callback_data=f'set:stickers:{cid}',style=ButtonStyle.SUCCESS)],[InlineKeyboardButton(text=f'📊 Media Details {s(c["media_details"])}',callback_data=f'set:media:{cid}',style=ButtonStyle.PRIMARY)],[InlineKeyboardButton(text='🗑 Remove',callback_data=f'remove:{cid}',style=ButtonStyle.DANGER),InlineKeyboardButton(text='↩️ Back',callback_data='channels',style=ButtonStyle.PRIMARY)]])

def has_media(m):return any((m.video,m.audio,m.document,m.photo,m.animation,m.voice,m.sticker))
def media_ok(m,f):
    if not f:return True
    t=(f.get('type') or '').lower(); return not t or bool({'video':m.video,'audio':m.audio,'document':m.document,'photo':m.photo,'animation':m.animation,'voice':m.voice,'sticker':m.sticker}.get(t))
async def report(bot,m,e):
    runtime['failed']+=1
    try: await bot.send_message(OWNER_ID,f'<b>🚨 Caption Bot Error</b>\n\n<b>Channel:</b> {m.chat.title or m.chat.id}\n<b>Message:</b> {m.message_id}\n<blockquote expandable><b>Reason:</b> {str(e)[:3000]}</blockquote>',parse_mode='HTML')
    except Exception:pass

@router.message(CommandStart())
async def start(m):
    if not await public_access(m):return
    text='👋 <b>Welcome to Auto Caption Bot</b>\n\n⚡ Multi-channel • Smart Caption • Colored Buttons'
    if START_PIC and os.path.exists(START_PIC):
        with open(START_PIC,'rb') as p:await m.answer_photo(p,caption=text,reply_markup=menu(),parse_mode='HTML')
    else:await m.answer(text,reply_markup=menu(),parse_mode='HTML')
@router.message(Command('help'))
async def help_cmd(m):
    if await public_access(m):await m.answer('<b>Help</b>\n\nUse /channels to add and configure channels. Each channel has separate settings.',parse_mode='HTML')
@router.message(Command('settings'))
async def settings_cmd(m):
    if await public_access(m):await m.answer('⚙️ Open /channels and select a channel.',reply_markup=menu())
@router.message(Command('channels'))
async def channels_cmd(m):
    if m.chat.type!='private':return
    if not await public_access(m):return
    rows=await db.list_channels(m.from_user.id);await m.answer(f'📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>',parse_mode='HTML',reply_markup=channel_menu(rows))
@router.message(Command('stats'))
async def stats_cmd(m):
    if not await public_access(m):return
    c=await db.counts();u=int(time.time()-started);await m.answer(f'📊 <b>Statistics</b>\n\n👥 Users: {c["users"]}\n📺 Channels: {c["channels"]}\n📥 Processed: {runtime["processed"]}\n✅ Edited: {runtime["edited"]}\n❌ Errors: {runtime["failed"]}\n⏱ Uptime: {u//86400}d {(u%86400)//3600}h {(u%3600)//60}m',parse_mode='HTML')
@router.message(Command('addadmin'))
async def addadmin(m):
    if await admin_only(m):
        try:await db.add_admin(int(m.text.split()[1]));await m.answer('✅ Admin added.')
        except:await m.answer('Usage: /addadmin USER_ID')
@router.message(Command('deladmin'))
async def deladmin(m):
    if await admin_only(m):
        try:await db.del_admin(int(m.text.split()[1]));await m.answer('✅ Admin removed.')
        except:await m.answer('Usage: /deladmin USER_ID')
@router.message(Command('set_public'))
async def setpublic(m):
    if await admin_only(m):await m.answer('Change PUBLIC_MODE in config.py and restart.')
@router.message(Command('broadcast'))
async def broadcast(m):
    if not await admin_only(m):return
    if not m.reply_to_message:return await m.answer('Reply to a message with /broadcast.')
    if db.db is not None:users=await db.db.users.find({}, {'user_id':1}).to_list(10000)
    else:users=[{'user_id':x[0]} for x in await (await db.sqlite.execute('SELECT user_id FROM users')).fetchall()]
    ok=bad=0
    for u in users:
        try:await m.reply_to_message.copy_to(u['user_id']);ok+=1
        except Exception:bad+=1
        await asyncio.sleep(.05)
    await m.answer(f'📢 Broadcast complete\n\n✅ Sent: {ok}\n❌ Failed: {bad}')

@router.callback_query(F.data=='home')
async def home(q):await q.message.edit_text('🤖 <b>Auto Caption Bot</b>',parse_mode='HTML',reply_markup=menu());await q.answer()
@router.callback_query(F.data=='help')
async def cbhelp(q):await q.message.edit_text('Use /channels to manage channels.',reply_markup=menu());await q.answer()
@router.callback_query(F.data=='settings')
async def cbsettings(q):await q.message.edit_text('⚙️ Select a channel from /channels.',reply_markup=menu());await q.answer()
@router.callback_query(F.data=='stats')
async def cbstats(q):
    c=await db.counts();await q.message.edit_text(f'📊 Users: {c["users"]}\n📺 Channels: {c["channels"]}\n📥 Processed: {runtime["processed"]}\n✅ Edited: {runtime["edited"]}\n❌ Errors: {runtime["failed"]}',reply_markup=menu());await q.answer()
@router.callback_query(F.data=='channels')
async def cbchannels(q):
    rows=await db.list_channels(q.from_user.id);await q.message.edit_text(f'📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>',parse_mode='HTML',reply_markup=channel_menu(rows));await q.answer()
@router.callback_query(F.data=='add_channel')
async def addchannel(q):states[q.from_user.id]={'type':'channel'};await q.message.edit_text('➕ <b>Add Channel</b>\n\nSend Channel ID or forward any channel message.\nBot must already be administrator.\n\n/cancel',parse_mode='HTML');await q.answer()
@router.callback_query(F.data.startswith('ch:'))
async def channel(q):
    cid=int(q.data.split(':')[1]);r=await db.get_channel(cid)
    if not r or r['owner_id']!=q.from_user.id:return await q.answer('Not your channel.',show_alert=True)
    await q.message.edit_text(f'📄 <b>{r["title"]}</b>\n🆔 <code>{cid}</code>\n🔗 @{r.get("username") or "private"}',parse_mode='HTML',reply_markup=settings_menu(cid,cfg(r)));await q.answer()
@router.callback_query(F.data.startswith('set:'))
async def setting(q):
    _,kind,cid=q.data.split(':');cid=int(cid);r=await db.get_channel(cid)
    if not r or r['owner_id']!=q.from_user.id:return await q.answer('Not your channel.',show_alert=True)
    c=cfg(r)
    if kind=='media':c['media_details']=not c['media_details']
    elif kind=='stickers':c['stickers']['enabled']=not c['stickers']['enabled']
    else:
        states[q.from_user.id]={'type':kind,'cid':cid};prompts={'caption':'📝 Send caption template.','buttons':'🔘 Button Text | URL | blue/green/red','replace':'🔄 old text | new text','filters':'🎯 video/audio/document/photo/animation/voice/sticker','forward':'📤 Destination channel ID.','prefix':'✨ Send prefix.','suffix':'✨ Send suffix.'};await q.message.edit_text(prompts[kind]+'\n\n/cancel');return await q.answer()
    await db.save_channel(r['owner_id'],cid,r['title'],r.get('username',''),json.dumps(c));await q.message.edit_reply_markup(reply_markup=settings_menu(cid,c));await q.answer()
@router.callback_query(F.data.startswith('remove:'))
async def remove(q):
    cid=int(q.data.split(':')[1]);r=await db.get_channel(cid)
    if not r or r['owner_id']!=q.from_user.id:return await q.answer('Not your channel.',show_alert=True)
    await db.delete_channel(cid,q.from_user.id);await q.message.edit_text('🗑 Channel removed.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='↩️ Channels',callback_data='channels',style=ButtonStyle.PRIMARY)]]));await q.answer()
@router.message(Command('cancel'))
async def cancel(m):states.pop(m.from_user.id,None);await m.answer('❌ Cancelled.')
@router.message(F.chat.type=='private')
async def private_input(m):
    st=states.get(m.from_user.id)
    if not st:return
    try:
        if st['type']=='channel':
            cid=getattr(getattr(m,'forward_origin',None),'chat',None);cid=cid.id if cid else int((m.text or '').strip());me=await m.bot.get_me();member=await m.bot.get_chat_member(cid,me.id)
            if member.status not in ('administrator','creator'):return await m.answer('❌ Bot must be administrator in this channel.')
            chat=await m.bot.get_chat(cid);await db.save_channel(m.from_user.id,cid,chat.title or 'Channel',chat.username or '',json.dumps(default_settings()));states.pop(m.from_user.id,None);return await m.answer(f'✅ <b>{chat.title}</b> added.',parse_mode='HTML',reply_markup=settings_menu(cid,default_settings()))
        cid=st['cid'];r=await db.get_channel(cid);c=cfg(r);t=m.text or m.caption or '';typ=st['type']
        if typ=='caption':c['caption']=t
        elif typ in ('prefix','suffix'):c[typ]=t
        elif typ=='replace':
            p=t.split('|',1)
            if len(p)!=2:return await m.answer('Use: old text | new text')
            c['replacements'][p[0].strip()]=p[1].strip()
        elif typ=='buttons':
            p=[x.strip() for x in t.split('|')]
            if len(p)!=3 or p[2].lower() not in ('blue','green','red'):return await m.answer('Use: Button Text | URL | blue/green/red')
            c['buttons'].append({'text':p[0],'url':p[1],'color':p[2].lower()})
        elif typ=='forward':c['forward']={'enabled':True,'destination':int(t)}
        elif typ=='filters':c['filters']={'type':t.lower()}
        await db.save_channel(r['owner_id'],cid,r['title'],r.get('username',''),json.dumps(c));states.pop(m.from_user.id,None);await m.answer('✅ Saved.',reply_markup=settings_menu(cid,c))
    except Exception as e:await report(m.bot,m,e)

@router.channel_post()
async def channel_post(m):
    r=await db.get_channel(m.chat.id)
    if not r or not has_media(m):return
    c=cfg(r)
    if not media_ok(m,c['filters']):return
    runtime['processed']+=1
    try:
        cap=format_caption(c['caption'],m) if c['caption'] else (m.caption or '')
        for a,b in c['replacements'].items():cap=cap.replace(a,b)
        if c['prefix']:cap=c['prefix']+'\n'+cap
        if c['suffix']:cap=cap+'\n'+c['suffix']
        bs=[InlineKeyboardButton(text=x['text'],url=x['url'],style=style(x.get('color'))) for x in c['buttons'] if x.get('text') and x.get('url')]
        mk=InlineKeyboardMarkup(inline_keyboard=[bs[i:i+2] for i in range(0,len(bs),2)]) if bs else None
        if cap!=m.caption or mk:await m.bot.edit_message_caption(m.chat.id,m.message_id,caption=cap or None,parse_mode='HTML',reply_markup=mk);runtime['edited']+=1
        if c['forward']['enabled'] and c['forward']['destination']:await m.bot.copy_message(c['forward']['destination'],m.chat.id,m.message_id)
    except TelegramRetryAfter as e:await asyncio.sleep(e.retry_after);await channel_post(m)
    except Exception as e:await report(m.bot,m,e)

async def main():
    await db.connect();bot=Bot(BOT_TOKEN);dp=Dispatcher();dp.include_router(router);await dp.start_polling(bot)
if __name__=='__main__':asyncio.run(main())
