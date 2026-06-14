from pathlib import Path
import os


def test_transcriber_generates_text(tmp_path, fake_whisper_run):
    from voxd.core.transcriber import WhisperTranscriber

    audio = tmp_path / "a.wav"; audio.write_bytes(b"\x00\x00")
    model = tmp_path / "m.bin"; model.write_bytes(b"x")
    binary = tmp_path / "whisper-cli"; binary.write_text("#!/bin/sh\n"); binary.chmod(0o755)

    t = WhisperTranscriber(str(model), str(binary), delete_input=True)
    text, orig = t.transcribe(str(audio))

    assert text == "Hello world"
    assert "Hello world" in (orig or "")
    assert not audio.exists()


_BLOCK = ["Подписывайтесь на мой канал, ставьте лайки и пишите комментарии."]


def test_is_hallucination_exact():
    from voxd.core.transcriber import is_hallucination
    assert is_hallucination("Подписывайтесь на мой канал, ставьте лайки и пишите комментарии.", _BLOCK)


def test_is_hallucination_case_and_whitespace_and_punct():
    from voxd.core.transcriber import is_hallucination
    # different case, extra spaces, missing trailing period
    assert is_hallucination("  ПОДПИСЫВАЙТЕСЬ  на мой   канал, ставьте лайки и пишите комментарии  ", _BLOCK)


def test_is_hallucination_repeated():
    from voxd.core.transcriber import is_hallucination
    phrase = "Подписывайтесь на мой канал, ставьте лайки и пишите комментарии. "
    assert is_hallucination(phrase * 2, _BLOCK)


def test_is_hallucination_real_speech_is_kept():
    from voxd.core.transcriber import is_hallucination
    assert not is_hallucination("привет, как дела", _BLOCK)


def test_is_hallucination_inside_real_text_is_kept():
    from voxd.core.transcriber import is_hallucination
    text = "Сегодня поговорим о Python. Подписывайтесь на мой канал, ставьте лайки и пишите комментарии. Начнём."
    assert not is_hallucination(text, _BLOCK)


def test_is_hallucination_disabled_when_no_blocklist():
    from voxd.core.transcriber import is_hallucination
    assert not is_hallucination("Подписывайтесь на мой канал, ставьте лайки и пишите комментарии.", [])


def test_parse_transcript_drops_hallucination(tmp_path):
    from voxd.core.transcriber import WhisperTranscriber

    model = tmp_path / "m.bin"; model.write_bytes(b"x")
    binary = tmp_path / "whisper-cli"; binary.write_text("#!/bin/sh\n"); binary.chmod(0o755)

    t = WhisperTranscriber(str(model), str(binary), hallucination_blocklist=_BLOCK)

    txt = tmp_path / "out.txt"
    txt.write_text("[00:00.000] Подписывайтесь на мой канал, ставьте лайки и пишите комментарии.\n", encoding="utf-8")
    tscript, orig = t._parse_transcript(txt)
    assert tscript == ""
    assert "Подписывайтесь" in (orig or "")


def test_parse_transcript_keeps_normal_text(tmp_path):
    from voxd.core.transcriber import WhisperTranscriber

    model = tmp_path / "m.bin"; model.write_bytes(b"x")
    binary = tmp_path / "whisper-cli"; binary.write_text("#!/bin/sh\n"); binary.chmod(0o755)

    t = WhisperTranscriber(str(model), str(binary), hallucination_blocklist=_BLOCK)

    txt = tmp_path / "out.txt"
    txt.write_text("[00:00.000] привет как дела\n", encoding="utf-8")
    tscript, _ = t._parse_transcript(txt)
    assert tscript == "привет как дела"


def test_transcriber_missing_input_raises(tmp_path):
    from voxd.core.transcriber import WhisperTranscriber

    model = tmp_path / "m.bin"; model.write_bytes(b"x")
    binary = tmp_path / "whisper-cli"; binary.write_text("#!/bin/sh\n"); binary.chmod(0o755)

    t = WhisperTranscriber(str(model), str(binary))
    missing = tmp_path / "does_not_exist.wav"
    try:
        t.transcribe(str(missing))
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError:
        pass


