from types import SimpleNamespace

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
        video=video,
        audio=None,
        document=None,
        photo=None,
        animation=None,
        voice=None,
    )


def test_dynamic_variables():
    result = format_caption(
        "{filename} | {episode} | S{season} | {quality} | {audio} | {resolution} | {duration}",
        message(),
    )
    assert "Anime.S02E07.1080p.Hindi.mkv" in result
    assert "07" in result
    assert "2" in result
    assert "1080p" in result
    assert "Hindi" in result
    assert "1920x1080" in result
    assert "0:02:00" in result


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
