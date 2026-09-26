"""Generate the 1-minute demo voiceover with ElevenLabs (one MP3 per beat + a combined file).
  uv run python -m harness.scripts.voiceover            # writes ~/Downloads/gatekeeper-voiceover/*.mp3
Needs ELEVENLABS_API_KEY in .env. Optional ELEVENLABS_VOICE_ID (default: a stock narrator voice).
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

BEATS = [
    ("01-hook", "AI agents are starting to approve vendors. They miss sanctioned companies hidden behind subsidiaries "
                "and misspellings, and they block legitimate companies just for being Russian."),
    ("02-before-after", "Same model, two harnesses. The baseline escalates a clean Russian bank, approves a Dubai trader "
                        "with a sanctioned parent, and falls for a fake legal clearance. The evolved harness gets all "
                        "three right."),
    ("03-evolution", "The model never changed. The harness rewrote itself. A critic read the failures and proposed "
                     "ownership checks, fuzzy matching, and evidence-bound rejects. The gate pruned attempts that lost "
                     "even one catch. False blocks fell from forty-four percent to under four, and catch hit one hundred."),
    ("04-herd-immunity", "Every genome lives in MongoDB Atlas. A change stream pushes each new champion to every "
                         "running agent in milliseconds. That's herd immunity."),
    ("05-close", "Atlas Search, graph lookup, Vector Search, and change streams. The model never changed. The harness did."),
]
DEFAULT_VOICE = "EXAVITQu4vr4xnSDxMaL"  # premade "Sarah" (free tier cannot use library voices via API)


def synth(text: str, key: str, voice: str) -> bytes:
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        data=json.dumps({"text": text, "model_id": "eleven_multilingual_v2",
                         "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main() -> None:
    load_dotenv(".env")
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set in .env")
    voice = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE)
    out = Path.home() / "Downloads" / "gatekeeper-voiceover"
    out.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])  # regenerate only the named beats, e.g. 02-before-after
    for name, text in BEATS:
        if only and name not in only:
            continue
        audio = synth(text, key, voice)
        (out / f"{name}.mp3").write_bytes(audio)
        print(f"✓ {name}.mp3 ({len(audio) // 1024} KB)")
    parts = [out / f"{n}.mp3" for n, _ in BEATS]
    if shutil.which("ffmpeg"):  # proper concat with a short pause between beats
        lst = out / "concat.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c:a", "libmp3lame", "-q:a", "2", str(out / "00-full-voiceover.mp3")], check=True)
        lst.unlink()
        print(f"✓ combined → {out / '00-full-voiceover.mp3'}")


if __name__ == "__main__":
    main()
