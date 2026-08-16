import json

def load(config):
    try: return json.loads(config or '{}').get('buttons',[])
    except Exception: return []
