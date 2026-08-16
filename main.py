import asyncio, json, logging, os, time
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from config import *
from database.db import Database
from utils.formatter import format_caption

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log=logging.getLogger('caption-bot')
router=Router(); db=Database(); states={}; started=time.time(); runtime={'processed':0,'edited':0,'failed':0}
DEFAULT={'caption':'','buttons':[],'replacements':{},'filters':{},'forward':{'enabled':False,'destination':None},'prefix':'','suffix':'','stickers':{'enabled':False},'media_details':False}

async def is_admin(uid): return await db.is_admin(uid)
async def access(m):
    await db.user_upsert(m.from_user.id, m.from_user.username or '')
    if await is_admin(m.from_user.id) or PUBLIC_MODE: return True
    await m.answer(f'🔒 This Bot Is Private\n\nPlease contact the administrator. {ADMIN_USERNAME}')
    return False
async def admin_access(m):
    if await is_admin(m.from_user.id): return True
    if not PUBLIC_MODE: await m.answer(f'🔒 This Bot Is Private\n\nPlease contact the administrator. {ADMIN_USERNAME}')
    else: await m.answer('❌ Admin only.')
    return False

def load(row):
    try: c=json.loads(row.get('config') or '{}')
    except Exception: c={}
    out=json.loads(json.dumps(DEFAULT));
    for k,v in c.items(): out[k]=v
    return out

def button_style(color):
    return {'blue':ButtonStyle.PRIMARY,'primary':ButtonStyle.PRIMARY,'green':ButtonStyle.SUCCESS,'success':ButtonStyle.SUCCESS,'red':ButtonStyle.DANGER,'danger':ButtonStyle.DANGER}.get((color or 'blue').lower(),ButtonStyle.PRIMARY)

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text='📺 Channels',callback_data='channels',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text='📊 Stats',callback_data='stats',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text='⚙️ Settings',callback_data='settings',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text='ℹ️ Help',callback_data='help',style=ButtonStyle.PRIMARY)]])

def channels_menu(rows):
    kb=[[InlineKeyboardButton(text=f"📢 {r.get('title','Channel')}",callback_data=f'ch:{r["channel_id"]}',style=ButtonStyle.PRIMARY)] for r in rows[:40]]
    kb += [[InlineKeyboardButton(text='➕ Add New Channel',callback_data='add_channel',style=ButtonStyle.SUCCESS)],[InlineKeyboardButton(text='↩️ Back',callback_data='home',style=ButtonStyle.PRIMARY)]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def settings_menu(cid,c):
    def state(v): return 'ON ✅' if v else 'OFF ❌'
    return InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text='📝 Caption',callback_data=f'set:caption:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text=f'🔘 Buttons ({len(c.get("buttons",[]))})',callback_data=f'set:buttons:{cid}',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text=f'🔄 Replace ({len(c.get("replacements",{}))})',callback_data=f'set:replace:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text=f'🎯 Filters {state(bool(c.get("filters")))}',callback_data=f'set:filters:{cid}',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text=f'📤 Forward {state(c.get("forward",{}).get("enabled"))}',callback_data=f'set:forward:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text=f'✨ Prefix {state(bool(c.get("prefix")))}',callback_data=f'set:prefix:{cid}',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text=f'✨ Suffix {state(bool(c.get("suffix")))}',callback_data=f'set:suffix:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text=f'🎉 Stickers {state(c.get("stickers",{}).get("enabled"))}',callback_data=f'set:stickers:{cid}',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text=f'📊 Media Details {state(c.get("media_details"))}',callback_data=f'set:media:{cid}',style=ButtonStyle.PRIMARY)],
      [InlineKeyboardButton(text='🗑 Remove Channel',callback_data=f'remove:{cid}',style=ButtonStyle.DANGER),InlineKeyboardButton(text='↩️ Back',callback_data='channels',style=ButtonStyle.PRIMARY)]])

def has_media(m): return any((m.video,m.audio,m.document,m.photo,m.animation,m.voice,m.sticker))

def media_filter_ok(m, filt):
    if not filt: return True
    t=(filt.get('type') or '').lower(); mp={'video':m.video,'audio':m.audio,'document':m.document,'photo':m.photo,'animation':m.animation,'voice':m.voice,'sticker':m.sticker}
    return not t or bool(mp.get(t))

async def safe_error(bot, m, exc):
    runtime['failed']+=1; text=f'<b>🚨 Caption Bot Error</b>\n\n<b>Channel:</b> {m.chat.title or m.chat.id}\n<b>Message:</b> {m.message_id}\n<blockquote expandable><b>Reason:</b> {str(exc)[:3000]}</blockquote>'
    try: await bot.send_message(OWNER_ID,text,parse_mode='HTML')
    except Exception: pass

async def apply_channel_post(bot,m):
    row=await db.get_channel(m.chat.id)
    if not row or not has_media(m): return
    c=load(row)
    if not media_filter_ok(m,c.get('filters')): return
    runtime['processed']+=1
    try:
        caption=format_caption(c.get('caption',''),m) if c.get('caption') else (m.caption or '')
        for a,b in c.get('replacements',{}).items(): caption=caption.replace(a,b)
        if c.get('prefix'): caption=c['prefix']+'\n'+caption
        if c.get('suffix'): caption=caption+'\n'+c['suffix']
        buttons=[]
        for b in c.get('buttons',[]):
            if b.get('text') and b.get('url'): buttons.append(InlineKeyboardButton(text=b['text'],url=b['url'],style=button_style(b.get('color'))))
        markup=InlineKeyboardMarkup(inline_keyboard=[buttons[i:i+2] for i in range(0,len(buttons),2)]) if buttons else None
        if caption and caption != (m.caption or '') or markup:
            await bot.edit_message_caption(m.chat.id,m.message_id,caption=caption or None,parse_mode='HTML',reply_markup=markup)
            runtime['edited']+=1
        f=c.get('forward',{}); dest=f.get('destination') if f.get('enabled') else None
        if dest: await bot.copy_message(dest,m.chat.id,m.message_id)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after); await apply_channel_post(bot,m)
    except Exception as e:
        await safe_error(bot,m,e)

@router.message(CommandStart())
async def start(m:Message):
    await db.user_upsert(m.from_user.id,m.from_user.username or '')
    if not PUBLIC_MODE and not await is_admin(m.from_user.id): return await m.answer(f'🔒 This Bot Is Private\n\nPlease contact the administrator. {ADMIN_USERNAME}')
    text='👋 <b>Welcome to Auto Caption Bot</b>\n\n⚡ Multi-channel • Smart Caption • Colored Buttons'
    if START_PIC and os.path.exists(START_PIC):
        with open(START_PIC,'rb') as p: await m.answer_photo(p,caption=text,reply_markup=main_menu(),parse_mode='HTML')
    else: await m.answer(text,reply_markup=main_menu(),parse_mode='HTML')

@router.message(Command('help'))
async def help_cmd(m):
    if await access(m): await m.answer('<b>Help</b>\n\nUse /channels to add and configure your channels. Every channel has independent caption, buttons, replace, filters, forward, prefix, suffix, stickers and media settings.',parse_mode='HTML')

@router.message(Command('settings'))
async def settings_cmd(m):
    if await access(m): await m.answer('⚙️ Select a channel from /channels to open its settings.',reply_markup=main_menu())

@router.message(Command('channels'))
async def channels_cmd(m):
    if not await access(m): return
    rows=await db.list_channels(m.from_user.id); await m.answer(f'📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>',parse_mode='HTML',reply_markup=channels_menu(rows))

@router.message(Command('stats'))
async def stats_cmd(m):
    if not await access(m): return
    c=await db.counts(); up=int(time.time()-started); await m.answer(f'📊 <b>Statistics</b>\n\n👥 Users: {c["users"]}\n📺 Channels: {c["channels"]}\n📥 Processed: {runtime["processed"]}\n✅ Edited: {runtime["edited"]}\n❌ Errors: {runtime["failed"]}\n⏱ Uptime: {up//86400}d {(up%86400)//3600}h {(up%3600)//60}m',parse_mode='HTML')

@router.message(Command('addadmin'))
async def add_admin_cmd(m):
    if not await admin_access(m): return
    try: uid=int(m.text.split(maxsplit=1)[1]); await db.add_admin(uid); await m.answer('✅ Admin added.')
    except: await m.answer('Usage: /addadmin USER_ID')

@router.message(Command('deladmin'))
async def del_admin_cmd(m):
    if not await admin_access(m): return
    try: uid=int(m.text.split(maxsplit=1)[1]); await db.del_admin(uid); await m.answer('✅ Admin removed.')
    except: await m.answer('Usage: /deladmin USER_ID')

@router.message(Command('set_public'))
async def set_public_cmd(m):
    if await admin_access(m): await m.answer('Change PUBLIC_MODE in config.py and restart the bot.')

@router.message(Command('broadcast'))
async def broadcast_cmd(m):
    if not await admin_access(m): return
    if not m.reply_to_message: return await m.answer('Reply to the message you want to broadcast with /broadcast.')
    users=[]
    if db.db is not None and DATABASE_TYPE.lower()=='mongodb': users=await db.db.users.find({}, {'user_id':1}).to_list(10000)
    else:
        cur=await db.sqlite.execute('SELECT user_id FROM users'); users=[{'user_id':x[0]} for x in await cur.fetchall()]
    ok=bad=0
    for u in users:
        try: await m.reply_to_message.copy_to(u['user_id']); ok+=1
        except Exception: bad+=1
        await asyncio.sleep(.05)
    await m.answer(f'📢 Broadcast complete\n\n✅ Sent: {ok}\n❌ Failed: {bad}')

@router.callback_query(F.data=='home')
async def home(q): await q.message.edit_text('🤖 <b>Auto Caption Bot</b>',parse_mode='HTML',reply_markup=main_menu()); await q.answer()
@router.callback_query(F.data=='help')
async def cb_help(q): await q.message.edit_text('Use /channels to manage channels. All channel settings are independent.',reply_markup=main_menu()); await q.answer()
@router.callback_query(F.data=='settings')
async def cb_settings(q): await q.message.edit_text('⚙️ Choose /channels to configure a channel.',reply_markup=main_menu()); await q.answer()
@router.callback_query(F.data=='stats')
async def cb_stats(q): await stats_cmd(q.message); await q.answer()
@router.callback_query(F.data=='channels')
async def cb_channels(q):
    rows=await db.list_channels(q.from_user.id); await q.message.edit_text(f'📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>',parse_mode='HTML',reply_markup=channels_menu(rows)); await q.answer()

@router.callback_query(F.data=='add_channel')
async def add_channel_cb(q): states[q.from_user.id]={'type':'channel'}; await q.message.edit_text('➕ <b>Add Channel</b>\n\nSend the Channel ID or forward any message from your channel here.\n\nThe bot must already be an administrator.\n\n/cancel',parse_mode='HTML'); await q.answer()

@router.callback_query(F.data.startswith('ch:'))
async def channel_cb(q):
    cid=int(q.data.split(':')[1]); row=await db.get_channel(cid)
    if not row or row['owner_id']!=q.from_user.id: return await q.answer('Not your channel.',show_alert=True)
    await q.message.edit_text(f'📄 <b>{row["title"]}</b>\n🆔 <code>{cid}</code>\n🔗 @{row.get("username") or "private"}',parse_mode='HTML',reply_markup=settings_menu(cid,load(row))); await q.answer()

@router.callback_query(F.data.startswith('set:'))
async def set_cb(q):
    _,kind,cid=q.data.split(':'); cid=int(cid); row=await db.get_channel(cid)
    if not row or row['owner_id']!=q.from_user.id: return await q.answer('Not your channel.',show_alert=True)
    c=load(row)
    if kind in ('media','stickers'):
        key='media_details' if kind=='media' else None
        if kind=='media': c[key]=not c.get(key)
        else: c['stickers']['enabled']=not c.get('stickers',{}).get('enabled')
        await db.save_channel(row['owner_id'],cid,row['title'],row.get('username',''),json.dumps(c)); await q.message.edit_reply_markup(reply_markup=settings_menu(cid,c)); return await q.answer()
    states[q.from_user.id]={'type':kind,'cid':cid}
    prompts={'caption':'📝 Send the complete caption template.','buttons':'🔘 Send: Button Text | URL | blue/green/red','replace':'🔄 Send: old text | new text','filters':'🎯 Send: video/audio/document/photo/animation/voice/sticker','forward':'📤 Send destination channel ID.','prefix':'✨ Send prefix.','suffix':'✨ Send suffix.'}
    await q.message.edit_text(prompts[kind]+'\n\n/cancel'); await q.answer()

@router.callback_query(F.data.startswith('remove:'))
async def remove_cb(q):
    cid=int(q.data.split(':')[1]); row=await db.get_channel(cid)
    if not row or row['owner_id']!=q.from_user.id: return await q.answer('Not your channel.',show_alert=True)
    await db.delete_channel(cid,q.from_user.id); await q.message.edit_text('🗑 Channel removed.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='↩️ Channels',callback_data='channels',style=ButtonStyle.PRIMARY)]])); await q.answer()

@router.message(Command('cancel'))
async def cancel(m): states.pop(m.from_user.id,None); await m.answer('❌ Cancelled.')

@router.message(F.chat.type=='private')
async def private_input(m):
    uid=m.from_user.id; st=states.get(uid)
    if not st: return
    try:
        if st['type']=='channel':
            cid=None; origin=getattr(m,'forward_origin',None)
            if origin and getattr(origin,'chat',None): cid=origin.chat.id
            if cid is None: cid=int((m.text or '').strip())
            me=await m.bot.get_me(); member=await m.bot.get_chat_member(cid,me.id)
            if member.status not in ('administrator','creator'): return await m.answer('❌ Bot must be an administrator in the channel.')
            chat=await m.bot.get_chat(cid); await db.save_channel(uid,cid,chat.title or 'Channel',chat.username or '',json.dumps(DEFAULT)); states.pop(uid,None)
            return await m.answer(f'✅ <b>{chat.title}</b> added.',parse_mode='HTML',reply_markup=settings_menu(cid,DEFAULT))
        cid=st['cid']; row=await db.get_channel(cid)
        if not row: states.pop(uid,None); return await m.answer('❌ Channel not found.')
        c=load(row); typ=st['type']; text=m.text or m.caption or ''
        if typ=='caption': c['caption']=text
        elif typ=='prefix': c['prefix']=text
        elif typ=='suffix': c['suffix']=text
        elif typ=='replace':
            p=text.split('|',1)
            if len(p)!=2: return await m.answer('Use: old text | new text')
            c['replacements'][p[0].strip()]=p[1].strip()
        elif typ=='buttons':
            p=[x.strip() for x in text.split('|')]
            if len(p)!=3 or p[2].lower() not in ('blue','green','red'): return await m.answer('Use: Button Text | URL | blue/green/red')
            c['buttons'].append({'text':p[0],'url':p[1],'color':p[2].lower()})
        elif typ=='forward': c['forward']={'enabled':True,'destination':int(text)}
        elif typ=='filters': c['filters']={'type':text.lower()}
        else: return
        await db.save_channel(row['owner_id'],cid,row['title'],row.get('username',''),json.dumps(c)); states.pop(uid,None); await m.answer('✅ Saved.',reply_markup=settings_menu(cid,c))
    except Exception as e: await safe_error(m.bot,m,e)

@router.channel_post()
async def on_channel_post(m): await apply_channel_post(m.bot,m)

async def main():
    await db.connect(); bot=Bot(BOT_TOKEN); dp=Dispatcher(); dp.include_router(router); log.info('Bot started'); await dp.start_polling(bot)

if __name__=='__main__': asyncio.run(main())
