"""Cookie validation and freshness check."""

import logging
import os
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

COOKIE_FILE = os.environ.get(
    "YT_COOKIES_PATH",
    "/opt/content-autopilot-v2/data/youtube_cookies.txt",
)
VS_COOKIE_FILE = "/home/meister/voicescriptor-web/data/cookies.txt"
MAX_COOKIE_AGE_HOURS = 24


def check_cookies() -> dict:
    """Check cookie status for both Content-Autopilot and VoiceScriptor."""
    result = {
        "autopilot_cookies": _check_file(COOKIE_FILE),
        "voicescriptor_cookies": _check_file(VS_COOKIE_FILE),
        "needs_refresh": False,
        "message": "",
    }

    ap = result["autopilot_cookies"]
    result["voicescriptor_cookies"]

    if not ap["exists"]:
        result["needs_refresh"] = True
        result["message"] = "Keine Cookies vorhanden. Bitte YouTube Cookies exportieren."
    elif ap["age_hours"] > MAX_COOKIE_AGE_HOURS:
        result["needs_refresh"] = True
        result["message"] = (
            f"Cookies sind {ap['age_hours']:.0f}h alt. Bitte neue Cookies exportieren (max {MAX_COOKIE_AGE_HOURS}h)."
        )
    elif ap["secure_count"] < 5:
        result["needs_refresh"] = True
        result["message"] = (
            "Cookies unvollstaendig. Bitte bei YouTube einloggen und erneut exportieren."
        )
    else:
        result["message"] = (
            f"Cookies OK ({ap['age_hours']:.0f}h alt, {ap['entry_count']} Eintraege)"
        )

    return result


def _check_file(path: str) -> dict:
    p = Path(path)
    if not p.exists() or p.stat().st_size < 100:
        return {"exists": False, "age_hours": 0, "entry_count": 0, "secure_count": 0}

    mtime = p.stat().st_mtime
    age_hours = (time.time() - mtime) / 3600

    content = p.read_text(encoding="utf-8", errors="ignore")
    lines = [l for l in content.split("\n") if l.strip() and not l.startswith("#")]
    secure_count = sum(1 for l in lines if "__Secure" in l)

    return {
        "exists": True,
        "age_hours": age_hours,
        "entry_count": len(lines),
        "secure_count": secure_count,
        "modified": datetime.fromtimestamp(mtime).isoformat(),
    }


def sync_cookies_to_voicescriptor() -> bool:
    """Copy cookies from Content-Autopilot to VoiceScriptor data dir."""
    src = Path(COOKIE_FILE)
    dst = Path(VS_COOKIE_FILE)

    if not src.exists():
        return False

    try:
        import shutil

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        # Fix permissions
        os.chmod(str(dst), 0o644)
        logger.info(f"Cookies synced to VoiceScriptor: {dst}")
        return True
    except Exception as e:
        logger.error(f"Cookie sync failed: {e}")
        # Try with sudo
        try:
            import subprocess

            subprocess.run(["sudo", "cp", str(src), str(dst)], check=True)
            subprocess.run(["sudo", "chmod", "644", str(dst)], check=True)
            return True
        except Exception:
            return False
