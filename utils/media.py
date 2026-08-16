def media_type(message):
    for name in ('video','audio','document','photo','animation','voice','sticker'):
        if getattr(message,name,None): return name
    return None
