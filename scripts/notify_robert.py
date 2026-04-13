#!/usr/bin/env python3
"""Sendet Telegram-Nachricht an Robert (Director-Config)."""
import sys, json, urllib.request

def load_config():
    try:
        with open("/opt/kolonie/director/config.json") as f:
            return json.load(f)
    except:
        return {}

def send(msg):
    cfg = load_config()
    tg = cfg.get("telegram", {})
    token = tg.get("bot_token", "")
    chat_id = tg.get("owner_chat_id", "")
    if not token or not chat_id:
        print("Telegram nicht konfiguriert", file=sys.stderr)
        return False
    payload = json.dumps({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown"
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.load(r)
            return result.get("ok", False)
    except Exception as e:
        print(f"Telegram Fehler: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Content Autopilot Agent Meldung"
    ok = send(msg)
    sys.exit(0 if ok else 1)
