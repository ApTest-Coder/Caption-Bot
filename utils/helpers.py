def clean_id(value):
    return int(str(value).strip())

def bool_value(value):
    return str(value).strip().lower() in {'1','true','yes','on'}
