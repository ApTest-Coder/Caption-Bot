DEFAULT_SETTINGS = {
    'caption':'','buttons':[],'replacements':{},'filters':{},
    'forward':{'enabled':False,'destination':None},'prefix':'','suffix':'',
    'stickers':{'enabled':False},'media_details':False
}

def default_settings():
    import copy
    return copy.deepcopy(DEFAULT_SETTINGS)
