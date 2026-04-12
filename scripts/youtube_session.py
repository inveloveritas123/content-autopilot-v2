"""
YouTube Session Manager
- Haelt eine echte Browser-Session auf dem Server am Leben
- Loggt sich ein (einmalig manuell), dann automatisch
- Spielt ab und zu Videos kurz an (normales Nutzerverhalten)
- Extrahiert frische Cookies fuer yt-dlp / VoiceScriptor
"""
import json, os, random, shutil, sqlite3, sys, time
from pathlib import Path

PROFILE_DIR = "/opt/content-autopilot/data/firefox-profile"
COOKIE_FILE = "/opt/content-autopilot/data/youtube_cookies.txt"
VS_COOKIE_FILE = "/home/meister/voicescriptor-web/data/cookies.txt"
STATUS_FILE = "/opt/content-autopilot/data/session_status.json"

SAMPLE_VIDEOS = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    "https://www.youtube.com/watch?v=9bZkp7q19f0",
    "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
    "https://www.youtube.com/watch?v=JGwWNGJdvx8",
    "https://www.youtube.com/watch?v=RgKAFK5djSk",
]


def save_status(status):
    Path(STATUS_FILE).write_text(json.dumps(status, indent=2))


def extract_cookies_from_profile():
    """Extract cookies from Firefox profile's cookies.sqlite."""
    db_path = None
    for p in Path(PROFILE_DIR).rglob("cookies.sqlite"):
        db_path = str(p)
        break
    if not db_path:
        return 0

    tmp = "/tmp/yt_cookies_copy.sqlite"
    shutil.copy2(db_path, tmp)

    conn = sqlite3.connect(tmp)
    cursor = conn.execute(
        "SELECT host, path, isSecure, expiry, name, value FROM moz_cookies "
        "WHERE host LIKE '%youtube%' OR host LIKE '%google%'"
    )

    lines = ["# Netscape HTTP Cookie File\n# Server Firefox - " + time.strftime("%Y-%m-%d %H:%M") + "\n"]
    count = 0
    has_sid = False
    for host, path, secure, expiry, name, value in cursor:
        if name == "SID":
            has_sid = True
        if not host.startswith("."):
            host = "." + host
        sec = "TRUE" if secure else "FALSE"
        lines.append(f"{host}\tTRUE\t{path}\t{sec}\t{expiry}\t{name}\t{value}")
        count += 1

    conn.close()
    os.unlink(tmp)

    if count > 5 and has_sid:
        Path(COOKIE_FILE).write_text("\n".join(lines))
        try:
            shutil.copy2(COOKIE_FILE, VS_COOKIE_FILE)
            os.chmod(VS_COOKIE_FILE, 0o644)
        except:
            os.system(f"sudo cp {COOKIE_FILE} {VS_COOKIE_FILE} && sudo chmod 644 {VS_COOKIE_FILE}")
        return count
    return 0


def simulate_usage():
    """Open YouTube, watch a random video briefly, extract cookies."""
    from playwright.sync_api import sync_playwright

    os.makedirs(PROFILE_DIR, exist_ok=True)

    with sync_playwright() as p:
        context = p.firefox.launch_persistent_context(
            PROFILE_DIR,
            headless=True,
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        )

        page = context.pages[0] if context.pages else context.new_page()

        # Go to YouTube homepage
        print("Opening YouTube...")
        page.goto("https://www.youtube.com", wait_until="networkidle", timeout=30000)
        time.sleep(random.uniform(2, 4))

        # Check if logged in
        cookies = context.cookies()
        has_sid = any(c["name"] == "SID" for c in cookies if ".google.com" in c.get("domain", ""))
        print(f"Logged in: {has_sid}")

        if not has_sid:
            save_status({"status": "not_logged_in", "time": time.strftime("%Y-%m-%d %H:%M")})
            context.close()
            return False

        # Watch a random video briefly (10-30 sec)
        video_url = random.choice(SAMPLE_VIDEOS)
        print(f"Watching: {video_url}")
        try:
            page.goto(video_url, wait_until="domcontentloaded", timeout=15000)
            watch_time = random.uniform(10, 30)
            print(f"Watching for {watch_time:.0f}s...")
            time.sleep(watch_time)
        except:
            pass

        # Back to homepage
        page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=15000)
        time.sleep(random.uniform(2, 5))

        context.close()

    # Extract cookies
    count = extract_cookies_from_profile()
    print(f"Extracted {count} cookies")

    save_status({
        "status": "ok" if count > 10 else "few_cookies",
        "cookies": count,
        "time": time.strftime("%Y-%m-%d %H:%M"),
        "video": video_url,
    })
    return count > 10


def login_interactive():
    """Start browser in visible mode for manual Google login."""
    from playwright.sync_api import sync_playwright

    os.makedirs(PROFILE_DIR, exist_ok=True)
    print("\nStarte Firefox fuer Google-Login...")
    print("Logge dich bei Google ein, dann schliesse den Browser.\n")

    with sync_playwright() as p:
        context = p.firefox.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            viewport={"width": 1280, "height": 720},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://accounts.google.com/ServiceLogin?service=youtube")

        # Wait until user closes browser
        try:
            while True:
                time.sleep(1)
                try:
                    _ = page.title()
                except:
                    break
        except KeyboardInterrupt:
            pass

        context.close()

    count = extract_cookies_from_profile()
    if count > 10:
        print(f"\nErfolgreich! {count} Cookies gespeichert.")
    else:
        print("\nLogin scheint nicht geklappt zu haben.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        login_interactive()
    elif len(sys.argv) > 1 and sys.argv[1] == "extract":
        count = extract_cookies_from_profile()
        print(f"{count} cookies extracted")
    else:
        simulate_usage()
