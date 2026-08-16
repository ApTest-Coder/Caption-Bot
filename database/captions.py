import json

def load(config):
    try: return json.loads(config or '{}').get('caption','')
    except Exception: return ''
