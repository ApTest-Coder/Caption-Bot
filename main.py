import asyncio, json, logging, os, re, time
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ButtonStyle
from database.db import Database
from config import BOT_TOKEN, OWNER_ID, PUBLIC_MODE, MAIN_CHANNEL, FSUB_CHANNEL, ADMIN_USERNAME, START_PIC, FSUB_PIC
from utils.formatter import format_caption

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log=logging.getLogger('caption-bot')
router=Router(); db=Database(); states={}; stats={'processed':0,'edited':0,'failed':0,'started':time.time()}

DEFAULT={
 'caption':'','buttons':[],'replacements':{},'filters':{},'forward':{'enabled':False,'destination':None},
 'prefix':'','suffix':'','stickers':{'enabled':False},'media_details':False
}

def is_media(m): return bool(m.video or m.audio or m.document or m.photo or m.animation or m.voice or m.sticker)
def cfg(row):
    try: c=json.loads(row.get('config') or '{}')
    except Exception: c={}
    out=json.loads(json.dumps(DEFAULT)); out.update(c); return out

def style(name):
    # Telegram Bot API button styles: primary/green/success/danger.
    return {'blue':ButtonStyle.PRIMARY,'primary':ButtonStyle.PRIMARY,'green':ButtonStyle.SUCCESS,'success':ButtonStyle.SUCCESS,'red':ButtonStyle.DANGER,'danger':ButtonStyle.DANGER}.get((name or 'blue').lower(),ButtonStyle.PRIMARY)

def menu(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text='📺 Channels',callback_data='channels',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text='📊 Stats',callback_data='stats',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text='⚙️ Settings',callback_data='global_settings',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text='ℹ️ Help',callback_data='help',style=ButtonStyle.PRIMARY)]])

def channel_list_markup(rows):
    kb=[]
    for r in rows[:30]: kb.append([InlineKeyboardButton(text=f"📢 {r.get('title','Channel')}",callback_data=f"ch:{r['channel_id']}",style=ButtonStyle.PRIMARY)])
    kb.append([InlineKeyboardButton(text='➕ Add New Channel',callback_data='add_channel',style=ButtonStyle.SUCCESS)])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def settings_markup(cid,c):
    def on(v): return 'ON ✅' if v else 'OFF ❌'
    return InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text='📝 Caption',callback_data=f'set:caption:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text='🔘 Buttons',callback_data=f'set:buttons:{cid}',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text='🔄 Replace',callback_data=f'set:replace:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text=f"🎯 Filters {on(bool(c.get('filters')))}",callback_data=f'set:filters:{cid}',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text=f"📤 Forward {on(c.get('forward',{}).get('enabled'))}",callback_data=f'set:forward:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text=f"✨ Prefix {on(bool(c.get('prefix')))}",callback_data=f'set:prefix:{cid}',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text=f"✨ Suffix {on(bool(c.get('suffix')))}",callback_data=f'set:suffix:{cid}',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text=f"🎉 Stickers {on(c.get('stickers',{}).get('enabled'))}",callback_data=f'set:stickers:{cid}',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text=f"📊 Media Details {on(c.get('media_details'))}",callback_data=f'set:media:{cid}',style=ButtonStyle.PRIMARY)],
      [InlineKeyboardButton(text='🗑 Remove Channel',callback_data=f'remove:{cid}',style=ButtonStyle.DANGER),InlineKeyboardButton(text='↩️ Back',callback_data='channels',style=ButtonStyle.PRIMARY)]
    ])

async def allowed(message: Message):
    if await db.is_admin(message.from_user.id): return True
    if PUBLIC_MODE: return True
    await message.answer(f'🔒 This Bot Is Private\n\nPlease contact the administrator. {ADMIN_USERNAME}')
    return False

async def admin_only(message: Message):
    if not await db.is_admin(message.from_user.id):
        if not PUBLIC_MODE: await message.answer(f'🔒 This Bot Is Private\n\nPlease contact the administrator. {ADMIN_USERNAME}')
        else: await message.answer('❌ Admin only.')
        return False
    return True

@router.message(CommandStart())
async def start(m: Message):
    await db.user_upsert(m.from_user.id, m.from_user.username or '')
    if not PUBLIC_MODE and not await db.is_admin(m.from_user.id):
        await m.answer(f'🔒 This Bot Is Private\n\nPlease contact the administrator. {ADMIN_USERNAME}')
        return
    text='👋 <b>Welcome to Auto Caption Bot</b>\n\nAutomatically edit captions, buttons and channel formatting.\n\n⚡ Fast • Multi-channel • Smart parser'
    if START_PIC and os.path.exists(START_PIC): await m.answer_photo(open(START_PIC,'rb'),caption=text,reply_markup=menu(m.from_user.id),parse_mode='HTML')
    else: await m.answer(text,reply_markup=menu(m.from_user.id),parse_mode='HTML')

@router.message(Command('help'))
async def help_cmd(m:Message):
    if not await allowed(m): return
    await m.answer('''<b>Help</b>\n\n/start — start bot\n/channels — manage channels\n/stats — statistics\n/settings — global settings\n\nAll channel configuration is handled from the button UI. Admin commands are restricted.''',parse_mode='HTML')

@router.message(Command('settings'))
async def settings_cmd(m:Message):
    if not await allowed(m): return
    await m.answer('⚙️ <b>Settings</b>\n\nChoose a channel from /channels to configure its caption, buttons, replace rules, filters, forwarding, prefix, suffix, stickers and media details.',parse_mode='HTML',reply_markup=menu(m.from_user.id))

@router.message(Command('channels'))
async def channels_cmd(m:Message):
    if not await allowed(m): return
    rows=await db.list_channels(m.from_user.id)
    await m.answer(f'📺 <b>Channel Settings</b>\n\nConnected Channels: <b>{len(rows)}</b>\n\nSelect a channel:',parse_mode='HTML',reply_markup=channel_list_markup(rows))

@router.message(Command('stats'))
async def stats_cmd(m:Message):
    if not await allowed(m): return
    c=await db.counts(); up=int(time.time()-stats['started']); await m.answer(f'📊 <b>Bot Statistics</b>\n\n👥 Users: {c["users"]}\n📺 Channels: {c["channels"]}\n📥 Processed: {stats["processed"]}\n✅ Edited: {stats["edited"]}\n❌ Errors: {stats["failed"]}\n⏱ Uptime: {up//3600}h {(up%3600)//60}m',parse_mode='HTML')

@router.message(Command('addadmin'))
async def addadmin(m:Message):
    if not await admin_only(m): return
    if len(m.text.split())<2: return await m.answer('Usage: /addadmin USER_ID')
    await db.add_admin(int(m.text.split()[1])); await m.answer('✅ Admin added.')

@router.message(Command('deladmin'))
async def deladmin(m:Message):
    if not await admin_only(m): return
    if len(m.text.split())<2: return await m.answer('Usage: /deladmin USER_ID')
    await db.del_admin(int(m.text.split()[1])); await m.answer('✅ Admin removed.')

@router.message(Command('broadcast'))
async def broadcast(m:Message):
    if not await admin_only(m): return
    if not m.reply_to_message: return await m.answer('Reply to a message with /broadcast.')
    rows=await db.db.users.find({}).to_list(10000) if hasattr(db,'db') and db.db is not None else []
    ok=bad=0
    for u in rows:
        try: await m.reply_to_message.copy_to(u['user_id']); ok+=1
        except Exception: bad+=1
        await asyncio.sleep(.05)
    await m.answer(f'📢 Broadcast finished.\n\n✅ Sent: {ok}\n❌ Failed: {bad}')

@router.message(Command('set_public'))
async def set_public(m:Message):
    if not await admin_only(m): return
    await m.answer('PUBLIC_MODE is configured in config.py. Restart the bot after changing it.')

@router.callback_query(F.data=='help')
async def cb_help(q:CallbackQuery): await q.message.edit_text('Use /channels to add and configure channels. Use the inline settings to manage each channel independently.'); await q.answer()

@router.callback_query(F.data=='stats')
async def cb_stats(q:CallbackQuery):
    c=await db.counts(); await q.message.edit_text(f'📊 Users: {c["users"]}\n📺 Channels: {c["channels"]}\n📥 Processed: {stats["processed"]}\n✅ Edited: {stats["edited"]}\n❌ Errors: {stats["failed"]}',reply_markup=menu(q.from_user.id)); await q.answer()

@router.callback_query(F.data=='channels')
async def cb_channels(q:CallbackQuery):
    if not await allowed(q.message): return await q.answer()
    rows=await db.list_channels(q.from_user.id); await q.message.edit_text(f'📺 <b>Channel Settings</b>\n\nConnected: {len(rows)}\n\nSelect a channel:',parse_mode='HTML',reply_markup=channel_list_markup(rows)); await q.answer()

@router.callback_query(F.data=='add_channel')
async def cb_add(q:CallbackQuery):
    states[q.from_user.id]={'state':'add_channel'}
    await q.message.edit_text('➕ <b>Add Channel</b>\n\nSend the Channel ID, or forward any message from your channel to me.\n\nThe bot must already be an administrator in that channel.',parse_mode='HTML'); await q.answer()

@router.message()
async def private_state(m:Message):
    uid=m.from_user.id
    st=states.get(uid)
    if not st or m.chat.type!='private': return
    if st['state']=='add_channel':
        cid=None
        origin=getattr(m,'forward_origin',None)
        if origin and getattr(origin,'chat',None): cid=origin.chat.id
        if not cid:
            try: cid=int((m.text or '').strip())
            except Exception: return await m.answer('❌ Send a valid channel ID or forward a channel message.')
        try:
            me=await m.bot.get_me(); member=await m.bot.get_chat_member(cid,me.id)
            if member.status not in ('administrator','creator'): return await m.answer('❌ Bot is not an administrator in this channel.')
            chat=await m.bot.get_chat(cid)
            await db.save_channel(uid,cid,chat.title or 'Channel',chat.username or '',json.dumps(DEFAULT))
            states.pop(uid,None); await m.answer(f'✅ Channel added successfully.\n\n📢 {chat.title}\n🆔 {cid}',reply_markup=settings_markup(cid,DEFAULT))
        except Exception as e: await m.answer(f'❌ Could not add channel.\nReason: {str(e)[:500]}')
        return
    cid=st.get('cid'); row=await db.get_channel(cid)
    if not row: states.pop(uid,None); return await m.answer('Channel not found.')
    c=cfg(row); kind=st['state']
    if kind=='caption': c['caption']=m.text or m.caption or ''; states.pop(uid,None)
    elif kind=='prefix': c['prefix']=m.text or ''; states.pop(uid,None)
    elif kind=='suffix': c['suffix']=m.text or ''; states.pop(uid,None)
    elif kind=='replace':
        parts=(m.text or '').split('|',1)
        if len(parts)!=2: return await m.answer('Format: old text | new text')
        c['replacements'][parts[0].strip()]=parts[1].strip(); states.pop(uid,None)
    elif kind=='buttons':
        parts=(m.text or '').split('|')
        if len(parts)<3: return await m.answer('Format: Button Text | URL | blue/green/red')
        c['buttons'].append({'text':parts[0].strip(),'url':parts[1].strip(),'color':parts[2].strip().lower()}); states.pop(uid,None)
    elif kind=='forward':
        try: c['forward']={'enabled':True,'destination':int((m.text or '').strip())}
        except: return await m.answer('Send destination channel ID.')
        states.pop(uid,None)
    elif kind=='filters':
        c['filters']={'type':(m.text or '').strip().lower()}; states.pop(uid,None)
    elif kind=='stickers': c['stickers']={'enabled':(m.text or '').strip().lower() in ('on','yes','true','1')}; states.pop(uid,None)
    else: return
    await db.save_channel(row['owner_id'],cid,row.get('title','Channel'),row.get('username',''),json.dumps(c)); await m.answer('✅ Setting saved.',reply_markup=settings_markup(cid,c))

@router.callback_query(F.data.startswith('ch:'))
async def cb_channel(q:CallbackQuery):
    cid=int(q.data.split(':')[1]); row=await db.get_channel(cid)
    if not row or row['owner_id']!=q.from_user.id: return await q.answer('Not your channel.',show_alert=True)
    await q.message.edit_text(f'📄 <b>{row.get("title","Channel")}</b>\n\n🆔 {cid}\n🔗 @{row.get("username") or "private"}',parse_mode='HTML',reply_markup=settings_markup(cid,cfg(row))); await q.answer()

@router.callback_query(F.data.startswith('set:'))
async def cb_setting(q:CallbackQuery):
    _,kind,cid_s=q.data.split(':'); cid=int(cid_s); row=await db.get_channel(cid)
    if not row or row['owner_id']!=q.from_user.id: return await q.answer('Not your channel.',show_alert=True)
    c=cfg(row)
    if kind=='media': c['media_details']=not c.get('media_details'); await db.save_channel(row['owner_id'],cid,row['title'],row.get('username',''),json.dumps(c)); await q.message.edit_reply_markup(reply_markup=settings_markup(cid,c)); return await q.answer()
    if kind=='stickers': c['stickers']['enabled']=not c.get('stickers',{}).get('enabled'); await db.save_channel(row['owner_id'],cid,row['title'],row.get('username',''),json.dumps(c)); await q.message.edit_reply_markup(reply_markup=settings_markup(cid,c)); return await q.answer()
    states[q.from_user.id]={'state':kind,'cid':cid}
    prompts={'caption':'📝 Send your caption template.','buttons':'🔘 Send: Button Text | URL | blue/green/red','replace':'🔄 Send: old text | new text','filters':'🎯 Send media type: video/audio/document/photo','forward':'📤 Send destination channel ID.','prefix':'✨ Send prefix text.','suffix':'✨ Send suffix text.'}
    await q.message.edit_text(prompts[kind]+'\n\n/cancel to cancel'); await q.answer()

@router.message(Command('cancel'))
async def cancel(m:Message): states.pop(m.from_user.id,None); await m.answer('❌ Cancelled.')

@router.callback_query(F.data.startswith('remove:'))
async def cb_remove(q:CallbackQuery):
    cid=int(q.data.split(':')[1]); row=await db.get_channel(cid)
    if not row or row['owner_id']!=q.from_user.id: return await q.answer('Not your channel.',show_alert=True)
    await db.delete_channel(cid,q.from_user.id); await q.message.edit_text('🗑 Channel removed.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='↩️ Channels',callback_data='channels',style=ButtonStyle.PRIMARY)]])); await q.answer()

@router.channel_post()
async def channel_post(m:Message):
    row=await db.get_channel(m.chat.id)
    if not row or not is_media(m) and not m.text: return
    c=cfg(row); stats['processed']+=1
    try:
        # Basic filter support.
        f=(c.get('filters') or {}).get('type')
        if f and f!='all':
            actual='video' if m.video else 'audio' if m.audio else 'document' if m.document else 'photo' if m.photo else 'animation' if m.animation else 'other'
            if actual!=f: return
        caption=c.get('caption','')
        if caption:
            new=format_caption(caption,m)
            for old,newval in c.get('replacements',{}).items(): new=new.replace(old,newval)
            if c.get('prefix'): new=f"{c['prefix']}\n{new}" if new else c['prefix']
            if c.get('suffix'): new=f"{new}\n{c['suffix']}" if new else c['suffix']
            kb=None
            if c.get('buttons'):
                rows=[]; current=[]
                for b in c['buttons']:
                    current.append(InlineKeyboardButton(text=b['text'],url=b['url'],style=style(b.get('color'))))
                    if len(current)==2: rows.append(current); current=[]
                if current: rows.append(current)
                kb=InlineKeyboardMarkup(inline_keyboard=rows)
            if m.caption is not None: await m.edit_caption(caption=new,reply_markup=kb,parse_mode='HTML')
            elif m.text is not None: await m.edit_text(text=new,reply_markup=kb,parse_mode='HTML')
            stats['edited']+=1
        # Optional forward: copy the edited message to destination.
        dest=c.get('forward',{}).get('destination') if c.get('forward',{}).get('enabled') else None
        if dest: await m.copy_to(dest)
    except Exception as e:
        stats['failed']+=1
        logging.exception('Channel processing failed')
        # Errors go to owner/admin DM only.
        text=f'<b><i>⚠️ Error while processing a channel post.</i></b>\n<blockquote expandable><b>Reason:</b> {str(e)[:3500]}</blockquote>'
        for aid in [OWNER_ID]:
            try: await m.bot.send_message(aid,text,parse_mode='HTML')
            except Exception: pass

async def main():
    if BOT_TOKEN.startswith('YOUR_') or OWNER_ID==123456789: raise RuntimeError('Configure config.py before running the bot.')
    await db.connect(); bot=Bot(BOT_TOKEN); dp=Dispatcher(); dp.include_router(router); log.info('Bot started'); await dp.start_polling(bot,allowed_updates=dp.resolve_used_update_types())

if __name__=='__main__': asyncio.run(main())
