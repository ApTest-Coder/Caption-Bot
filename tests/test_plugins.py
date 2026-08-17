from types import SimpleNamespace

from plugins.buttons import normalize_button, validate_button
from plugins.context import _safe_settings, valid_http_url
from plugins.filters import validate_filter
from plugins.forward import parse_destination
from plugins.replace import apply, validate_rule


def test_button_validation_and_normalization():
    valid, reason = validate_button("Join", "https://t.me/example", "green")
    assert valid is True
    assert reason == ""
    assert normalize_button(" Join ", "https://t.me/example", "GREEN") == {
        "text": "Join",
        "url": "https://t.me/example",
        "color": "green",
    }


def test_button_validation_rejects_bad_url_and_color():
    valid, _ = validate_button("Join", "@example", "green")
    assert valid is False
    valid, _ = validate_button("Join", "https://t.me/example", "purple")
    assert valid is False


def test_filter_validation():
    assert validate_filter(" VIDEO ")[0] is True
    assert validate_filter("movie")[0] is False


def test_forward_destination_parser():
    assert parse_destination("-1001234567890") == -1001234567890
    assert parse_destination("123456") == 123456
    assert parse_destination("0") is None
    assert parse_destination("abc") is None


def test_replace_validation_and_application():
    assert validate_rule("old", "new")[0] is True
    assert validate_rule(" ", "new")[0] is False
    assert apply("old old", {"old": "new"}) == "new new"


def test_settings_are_sanitized_before_ui_use():
    settings = _safe_settings(
        {
            "buttons": ["bad", {"text": "Join", "url": "https://t.me/x"}],
            "forward": None,
            "filters": {"type": "unknown"},
            "stickers": {"enabled": "yes"},
            "media_details": "true",
        }
    )
    assert settings["buttons"] == [
        {"text": "Join", "url": "https://t.me/x"},
    ]
    assert settings["forward"] == {"enabled": False, "destination": None}
    assert settings["filters"] == {}
    assert settings["stickers"] == {"enabled": False}
    assert settings["media_details"] is False


def test_url_validation():
    assert valid_http_url("https://example.com") is True
    assert valid_http_url("tg://resolve?domain=example") is False
    assert valid_http_url("@example") is False


def test_caption_media_capability():
    from plugins.caption import supports_caption_edit

    video = SimpleNamespace(
        video=object(),
        audio=None,
        document=None,
        photo=None,
        animation=None,
        voice=None,
        sticker=None,
    )
    sticker = SimpleNamespace(
        video=None,
        audio=None,
        document=None,
        photo=None,
        animation=None,
        voice=None,
        sticker=object(),
    )
    assert supports_caption_edit(video) is True
    assert supports_caption_edit(sticker) is False
