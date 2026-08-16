def apply(text, rules):
    for old,new in (rules or {}).items(): text=text.replace(old,new)
    return text
