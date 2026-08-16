import re

RES_RE = re.compile(r'(?<!\d)(\d{3,4})[pP](?!\w)|\b(\d{3,4})[xX](\d{3,4})\b')
EP_RE = re.compile(r'(?i)(?:S\d{1,2}[ ._-]*)?E(?:P(?:ISODE)?)?[ ._-]*(\d{1,4})|(?:EP(?:ISODE)?|E)[ ._-]*(\d{1,4})')
SEASON_RE = re.compile(r'(?i)\bS(?:EASON)?[ ._-]?(\d{1,2})\b')
YEAR_RE = re.compile(r'\b(19\d{2}|20\d{2})\b')
LANGS = ['Hindi','English','Japanese','Tamil','Telugu','Bengali','Korean','Chinese','Arabic','French','Spanish','German']

def parse_filename(name: str):
    text=name or ''
    out={}
    m=EP_RE.search(text); out['episode']=(m.group(1) or m.group(2)) if m else None
    m=SEASON_RE.search(text); out['season']=m.group(1) if m else None
    m=RES_RE.search(text)
    if m: out['quality'] = f'{m.group(1)}p' if m.group(1) else f'{m.group(3)}p'
    else: out['quality']=None
    m=YEAR_RE.search(text); out['year']=m.group(1) if m else None
    low=text.lower(); out['language']=next((x for x in LANGS if x.lower() in low), None)
    if re.search(r'(?i)\bhindi\b', text): out['audio']='Hindi'
    elif out['language']: out['audio']=out['language']
    else: out['audio']=None
    return out

def media_values(message):
    v={}
    if message.video:
        m=message.video; v.update(filename=m.file_name, filesize=m.file_size, duration=m.duration, width=m.width, height=m.height, mime_type=m.mime_type)
    elif message.audio:
        m=message.audio; v.update(filename=m.file_name, filesize=m.file_size, duration=m.duration, title=m.title, artist=m.performer, mime_type=m.mime_type)
    elif message.document:
        m=message.document; v.update(filename=m.file_name, filesize=m.file_size, mime_type=m.mime_type)
    elif message.photo:
        m=message.photo; v.update(filesize=m.file_size, width=m.width, height=m.height, mime_type='image/jpeg')
    elif message.animation:
        m=message.animation; v.update(filename=m.file_name, filesize=m.file_size, duration=m.duration, width=m.width, height=m.height, mime_type=m.mime_type)
    return {k:x for k,x in v.items() if x is not None}
