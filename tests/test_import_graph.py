from importlib import import_module


MODULES = (
    "main",
    "database",
    "database.buttons",
    "database.captions",
    "database.channels",
    "database.mongo",
    "database.settings",
    "database.sqlite",
    "database.users",
    "plugins.about",
    "plugins.admin",
    "plugins.broadcast",
    "plugins.buttons",
    "plugins.callbacks",
    "plugins.caption",
    "plugins.channels",
    "plugins.context",
    "plugins.filters",
    "plugins.forward",
    "plugins.fsub",
    "plugins.help",
    "plugins.replace",
    "plugins.start",
    "plugins.status",
    "plugins.users",
    "utils.errors",
    "utils.floodwait",
    "utils.formatter",
    "utils.helpers",
    "utils.html",
    "utils.logger",
    "utils.media",
    "utils.parser",
    "utils.retry",
    "utils.validation",
    "utils.variables",
)


def test_all_project_modules_import():
    """Every package module must import successfully through the real graph."""
    for module_name in MODULES:
        import_module(module_name)


def test_dispatcher_registers_feature_routers():
    """The entry point must actually register every handler router."""
    main = import_module("main")
    dispatcher = main.build_dispatcher()
    handler_count = sum(len(router.message.handlers) + len(router.callback_query.handlers) for router in dispatcher.sub_routers)
    assert handler_count >= 20
