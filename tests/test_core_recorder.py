def test_recorder_start_stop_creates_file(tmp_path, monkeypatch):
    # Use stubbed sounddevice from conftest
    from voxd.core.recorder import AudioRecorder
    # Force non-chunked (simplify)
    rec = AudioRecorder(samplerate=16000, channels=1, record_chunked=False)
    rec.start_recording()
    # Simulate no incoming data; stop should still create an empty WAV
    out = rec.stop_recording(preserve=False)
    assert out.exists()


def test_save_wav_resamples_fallback_rate_to_16k(tmp_path):
    """When capture fell back to a non-16 kHz rate, the saved WAV must be 16 kHz
    so whisper-cli (which only accepts 16 kHz) can read it."""
    import wave
    import numpy as np
    from voxd.core.recorder import AudioRecorder, WHISPER_FS

    rec = AudioRecorder(samplerate=16000, channels=1, record_chunked=False)
    rec.fs = 48000  # simulate the device-default-rate fallback

    # 1 s of audio at 48 kHz → expect ~16000 frames at 16 kHz output
    data = np.zeros((48000, 1), dtype=np.float32)
    out = tmp_path / "out.wav"
    rec._save_wav(data, out)

    with wave.open(str(out), "r") as wf:
        assert wf.getframerate() == WHISPER_FS
        assert abs(wf.getnframes() - 16000) <= 2

