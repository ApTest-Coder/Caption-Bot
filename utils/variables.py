"""Supported caption placeholders."""
VIDEO={'filename','filesize','duration','height','width','resolution','ext','mime_type'}
AUDIO={'title','artist','duration','filename','filesize','ext','mime_type'}
PHOTO={'caption','html_caption','filesize','width','height','mime_type','wish'}
DOCUMENT={'filename','filesize','ext','mime_type'}
COMMON={'caption','html_caption','language','year','quality','season','episode','wish','audio'}
ALL=VIDEO|AUDIO|PHOTO|DOCUMENT|COMMON
