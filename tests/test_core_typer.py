def test_detect_backend_env(monkeypatch):
    from voxd.core.typer import detect_backend
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert detect_backend() == "wayland"


def test_typer_paste_path(monkeypatch):
    from voxd.core.typer import SimulatedTyper
    # Disable tools so it falls back to paste
    monkeypatch.setenv("WAYLAND_DISPLAY", "")
    monkeypatch.setenv("DISPLAY", "")
    t = SimulatedTyper(delay=0, start_delay=0)
    # Emulate no tool available
    t.tool = None
    # Should not raise
    t.type("hello")


def test_will_paste_unicode(monkeypatch):
    from voxd.core.typer import SimulatedTyper
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    t = SimulatedTyper(delay=10, start_delay=0)
    t.enabled = True
    t.tool = "/usr/bin/ydotool"

    # ASCII with positive delay → key emulation
    assert t.will_paste("hello") is False
    # Cyrillic forces paste regardless of delay
    assert t.will_paste("привет") is True
    # zero delay always pastes
    t.delay_ms = 0
    assert t.will_paste("hello") is True


def test_paste_preserves_clipboard(monkeypatch):
    """_paste should snapshot the existing clipboard and restore it after paste."""
    import sys, types
    import voxd.core.typer as typer_mod
    from voxd.core.typer import SimulatedTyper

    pc = sys.modules["pyperclip"]
    pc._store["last"] = "USER_ORIGINAL"  # type: ignore[attr-defined]

    # Stub the paste-keystroke subprocess.run so we don't actually launch tools.
    monkeypatch.setattr(typer_mod.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))
    # Make the post-paste sleep instant so the test stays fast.
    monkeypatch.setattr(typer_mod.time, "sleep", lambda *_a, **_k: None)

    class _Cfg:
        data = {
            "paste_preserve_clipboard": True,
            "paste_restore_delay_ms": 0,
            "append_trailing_space": False,
            "ctrl_v_paste": False,
        }

    t = SimulatedTyper(delay=0, start_delay=0, cfg=_Cfg())
    t.enabled = True
    t.tool = "/usr/bin/ydotool"
    t._paste("Привет")

    assert pc._store["last"] == "USER_ORIGINAL", (  # type: ignore[attr-defined]
        f"clipboard was not restored, got: {pc._store['last']!r}"  # type: ignore[attr-defined]
    )


def test_paste_no_restore_when_caller_pre_copied(monkeypatch):
    """If the saved snapshot equals the transcript (caller pre-copied),
    skip restoration — there's nothing useful to restore."""
    import sys, types
    import voxd.core.typer as typer_mod
    from voxd.core.typer import SimulatedTyper

    pc = sys.modules["pyperclip"]
    pc._store["last"] = "TRANSCRIPT"  # type: ignore[attr-defined]

    monkeypatch.setattr(typer_mod.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))
    monkeypatch.setattr(typer_mod.time, "sleep", lambda *_a, **_k: None)

    class _Cfg:
        data = {
            "paste_preserve_clipboard": True,
            "paste_restore_delay_ms": 0,
            "append_trailing_space": False,
            "ctrl_v_paste": False,
        }

    t = SimulatedTyper(delay=0, start_delay=0, cfg=_Cfg())
    t.enabled = True
    t.tool = "/usr/bin/ydotool"
    t._paste("TRANSCRIPT")

    # Clipboard ends up as the transcript itself — no restore loop needed.
    assert pc._store["last"] == "TRANSCRIPT"  # type: ignore[attr-defined]

