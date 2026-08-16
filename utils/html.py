from html import escape

def escape_text(text):
    return escape(text or '', quote=False)
