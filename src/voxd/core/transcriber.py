import subprocess
import os
from pathlib import Path
import re
from voxd.utils.libw import verbo, verr
from voxd.paths import find_whisper_cli, find_base_model
from voxd.utils.languages import normalize_lang_code, is_valid_lang


# Whisper.cpp occasionally hallucinates "YouTube boilerplate" (subscribe/like
# phrases from its training data) when fed silence or noise. These helpers let
# us drop a transcript that consists *solely* of such a known phrase.
_PUNCT_STRIP = " \t\n.,!?…\"'«»—–-:;()"


def _normalize_for_match(text: str) -> str:
    """Lower-case, collapse whitespace, strip edge punctuation for comparison."""
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text.strip(_PUNCT_STRIP)


def is_hallucination(text: str, blocklist) -> bool:
    """True if ``text`` is entirely one blocklisted phrase (or repeats of one)."""
    if not text or not blocklist:
        return False
    norm = _normalize_for_match(text)
    if not norm:
        return False
    for phrase in blocklist:
        pnorm = _normalize_for_match(str(phrase))
        if not pnorm:
            continue
        if norm == pnorm:
            return True
        # Whisper sometimes repeats the same hallucination back-to-back.
        # Remove every occurrence of the phrase; if nothing meaningful is
        # left, the transcript was nothing but repeats of that phrase.
        remainder = norm.replace(pnorm, "")
        if not remainder.strip(_PUNCT_STRIP):
            return True
    return False


class WhisperTranscriber:
    def __init__(self, model_path, binary_path, delete_input=True, language: str | None = None,
                 filter_hallucinations: bool | None = None,
                 hallucination_blocklist: list[str] | None = None):
        # --- Model path: try config, else auto-discover ---
        if model_path and Path(model_path).is_file():
            self.model_path = model_path
        else:
            # Try to use the default model in cache
            self.model_path = find_base_model()
            verbo(f"[transcriber] Falling back to cached model: {self.model_path}")

        # --- Binary path: try config, else auto-discover ---
        if binary_path and Path(binary_path).is_file() and os.access(binary_path, os.X_OK):
            self.binary_path = binary_path
        else:
            self.binary_path = find_whisper_cli()
            verbo(f"[transcriber] Falling back to auto-detected whisper-cli: {self.binary_path}")

        self.delete_input = delete_input
        from voxd.paths import OUTPUT_DIR
        self.output_dir = OUTPUT_DIR

        # Language (default en)
        lang = normalize_lang_code(language or "en")
        if not is_valid_lang(lang):
            verr(f"[transcriber] Invalid language '{language}', using 'en'")
            lang = "en"
        self.language = lang

        # Hallucination filtering (lazily pull defaults from the shared config)
        if filter_hallucinations is None or hallucination_blocklist is None:
            try:
                from voxd.core.config import get_config
                cfg = get_config()
                if filter_hallucinations is None:
                    filter_hallucinations = cfg.data.get("hallucination_filter_enabled", True)
                if hallucination_blocklist is None:
                    hallucination_blocklist = cfg.data.get("hallucination_blocklist", [])
            except Exception:
                pass
        self.filter_hallucinations = bool(filter_hallucinations) if filter_hallucinations is not None else True
        self.hallucination_blocklist = hallucination_blocklist or []

        # Warn if likely mismatch with an English-only model
        try:
            mp = str(self.model_path).lower()
            if self.language != "en" and mp.endswith(".en.bin"):
                verr("[transcriber] Non-English language selected but an English-only (*.en) model is configured.")
        except Exception:
            pass

    def transcribe(self, audio_path):
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"[transcriber] Audio file not found: {audio_file}")

        verbo(f"[transcriber] Using binary: {self.binary_path}")
        verbo(f"[transcriber] Using model: {self.model_path}")
        verbo("[transcriber] Starting transcription...")

        # Output prefix (no extension!)
        output_prefix = self.output_dir / audio_file.stem
        output_txt = output_prefix.with_suffix(".txt")

        cmd = [
            self.binary_path,
            "-m", self.model_path,
            "-f", str(audio_file),
            "-l", self.language,
            "-of", str(self.output_dir / audio_file.stem),
            "-otxt"  # <-- THIS is necessary to actually generate the .txt file
        ]

        verbo(f"[transcriber] Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            verr("[transcriber] whisper.cpp failed:")
            verr(f"stderr: {result.stderr}")
            verr(f"stdout: {result.stdout}")
            return None, None

        if not output_txt.exists():
            verr(f"[transcriber] Transcription failed: Expected output not found at {output_txt}")
            return None, None

        verbo(f"[transcriber] Transcription complete: {output_txt}")

        # Optionally delete the input audio
        if self.delete_input:
            try:
                audio_file.unlink()
                verbo(f"[transcriber] Deleted input file: {audio_file}")
            except Exception as e:
                verr(f"[transcriber] Could not delete input file: {e}")

        return self._parse_transcript(output_txt)

    def _parse_transcript(self, path: Path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"[transcriber] Failed to read transcript file: {e}")
            return None, None

        orig_tscript = "".join(lines)

        # Strip timestamps like [00:00.000] or (00:00)
        tscript = re.sub(r"\[\d{2}:\d{2}[\.:]\d{3}\]|\(\d{2}:\d{2}\)", "", orig_tscript)
        tscript = re.sub(r"\s+", " ", tscript).strip()

        if self.filter_hallucinations and tscript and \
           is_hallucination(tscript, self.hallucination_blocklist):
            verbo(f"[transcriber] Dropped hallucination: {tscript!r}")
            return "", orig_tscript

        return tscript, orig_tscript
