from types import SimpleNamespace

from plugins.caption import apply_replacements
from utils.formatter import format_caption


def message(filename="Anime.S02E07.1080p.Hindi.mkv", caption=""):
    video = SimpleNamespace(
        file_name=filename,
        file_size=1048576,
        duration=120,
        width=1920,
        height=1080,
        mime_type="video/x-matroska",
    )
    return SimpleNamespace(
        caption=caption,
        text=None,
        html_caption=None,
        html_text=None,
        video=video,
        audio=None,
        document=None,
        photo=None,
        animation=None,
        voice=None,
        sticker=None,
    )


def test_dynamic_variables():
    result = format_caption(
        "{filename} | {episode} | S{season} | {quality} | {audio} | {resolution} | {duration}",
        message(),
    )
    assert "Anime.S02E07.1080p.Hindi.mkv" in result
    assert "07" in result
    assert "S02" in result
    assert "1080p" in result
    assert "Hindi" in result
    assert "1920x1080" in result
    assert "0:02:00" in result


def test_audio_language_is_detected_from_filename():
    result = format_caption("{audio}", message(filename="Show.S01E01.English.720p.mkv"))
    assert result == "English"


def test_season_with_no_separator_before_episode():
    """SxxEyy must resolve the season even without a separator."""
    result = format_caption("{season}", message(filename="Show.S09E12.720p.mkv"))
    assert result == "09"


def test_resolution_token_uses_video_dimensions():
    """A WxH token keeps resolution while quality follows the height."""
    result = format_caption(
        "Quality={quality}\nResolution={resolution}",
        message(filename="Show.S01E01.1920x1080.mkv"),
    )
    assert result == "Quality=1080p\nResolution=1920x1080"


def test_episode_season_and_quality_fallbacks():
    result = format_caption(
        "E={episode}\nS={season}\nQ={quality}\nA={audio}",
        message(filename="unknown_file.mkv"),
    )
    assert "E01 - E0?" in result
    assert "S01 - S0?" in result
    assert "Unknown Quality" in result
    assert "Audio" in result
    assert "(?)" not in result


def test_missing_optional_line_is_skipped():
    result = format_caption(
        "Keep\nDuration: {duration}\nTitle: {title}\n",
        message(filename="plain.mkv"),
    )
    assert result == "Keep\nDuration: 0:02:00"


def test_photo_metadata_uses_largest_photo_size():
    photo = SimpleNamespace(
        file_size=2048,
        width=1920,
        height=1080,
    )
    msg = SimpleNamespace(
        caption="",
        text=None,
        html_caption=None,
        html_text=None,
        video=None,
        audio=None,
        document=None,
        photo=[
            SimpleNamespace(file_size=512, width=90, height=90),
            photo,
        ],
        animation=None,
        voice=None,
        sticker=None,
    )
    result = format_caption(
        "{filesize} | {resolution} | {mime_type}",
        msg,
    )
    assert result == "2.00 KB | 1920x1080 | image/jpeg"


def test_dynamic_metadata_is_html_escaped():
    result = format_caption(
        "<b>{filename}</b>\n<blockquote>{caption}</blockquote>",
        message(filename="A&B <test>.mkv", caption="Tom & <Jerry>"),
    )
    assert "A&amp;B &lt;test&gt;.mkv" in result
    assert "Tom &amp; &lt;Jerry&gt;" in result


def test_replacements_do_not_corrupt_html_entities():
    result = apply_replacements(
        "<b>A&amp;B</b> &lt;test&gt;",
        {"&": " and "},
    )
    assert result == "<b>A and B</b> &lt;test&gt;"


def test_html_caption_fallback_is_escaped():
    msg = message(caption="Tom & <Jerry>")
    result = format_caption("{html_caption}", msg)
    assert result == "Tom &amp; &lt;Jerry&gt;"


def test_html_caption_property_is_preserved():
    msg = message(caption="ignored")
    msg.html_caption = "<b>Formatted</b>"
    result = format_caption("{html_caption}", msg)
    assert result == "<b>Formatted</b>"
