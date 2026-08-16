import logging
log=logging.getLogger('caption-bot')

def log_exception(exc):
    log.exception('Unhandled bot error: %s',exc)
