import re
from datetime import datetime
from .parser import parse_filename, media_values

TOKEN_RE=re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')


def human_size(n):
    if n is None: return None
    n=float(n); units=['B','KB','MB','GB','TB']; i=0
    while n>=1024 and i<len(units)-1: n/=1024; i+=1
    return f'{n:.2f} {units[i]}'

def format_caption(template, message):
    original = message.caption or message.text or ''
    values=media_values(message)
    filename=values.get('filename') or ''
    parsed=parse_filename(filename)
    # Caption is a second source for episode/season/quality/language.
    capparsed=parse_filename(original)
    for key in ('episode','season','quality','year','language','audio'):
        if not parsed.get(key): parsed[key]=capp = capparsed.get(key)
    values.update(parsed)
    values['caption']=re.sub(r'<[^>]+>','',original)
    values['html_caption']=original
    values['ext']=(filename.rsplit('.',1)[-1] if '.' in filename else None)
    values['resolution']=(f"{values['width']}x{values['height']}" if values.get('width') and values.get('height') else None)
    values['filesize']=human_size(values.get('filesize'))
    values['wish']=wish()
    values['audio']=values.get('audio') or 'Audio'
    values['episode']=values.get('episode') or 'E01 - E0? (?)'
    values['season']=values.get('season') or 'S01 - S0? (?)'
    values['quality']=values.get('quality') or 'Unknown Quality'
    # Other missing values are skipped by dropping the entire line containing the token.
    tokens=set(TOKEN_RE.findall(template))
    special={'episode','season','quality','audio'}
    for line in template.splitlines():
        found=TOKEN_RE.findall(line)
        if found and any((t not in special and not values.get(t)) for t in found):
            template=template.replace(line,'')
    def repl(m):
        k=m.group(1)
        if k in values and values[k] is not None: return str(values[k])
        return ''
    result=TOKEN_RE.sub(repl, template)
    return '\n'.join(x.rstrip() for x in result.splitlines()).strip()

def wish():
    h=datetime.now().hour
    return 'Good Morning' if h<12 else ('Good Afternoon' if h<17 else 'Good Evening')
