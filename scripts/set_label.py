#!/usr/bin/env python3
"""Setzt ein Label auf ein Gitea Issue (via ISSUE_NR_VAL env var)."""
import sys, json, os, urllib.request

GITEA_API = "http://localhost:3000/api/v1/repos/meister/content-autopilot-v2"
TOKEN = os.environ["GITEA_TOKEN"]  # Secret entfernt bei GitHub-Migration; aus Umgebung lesen

issue_nr = int(os.environ.get("ISSUE_NR_VAL", "0"))
label_name = sys.argv[1] if len(sys.argv) > 1 else "wartet-auf-freigabe"
label_color = sys.argv[2] if len(sys.argv) > 2 else "#FF6B6B"

def api(method, path, data=None):
    url = f"{GITEA_API}{path}?token={TOKEN}"
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception as e:
        print(f"API-Fehler {method} {path}: {e}", file=sys.stderr)
        return {}

if not issue_nr:
    print("ISSUE_NR_VAL nicht gesetzt", file=sys.stderr)
    sys.exit(1)

# Label-ID ermitteln oder neu erstellen
labels = api("GET", "/labels")
label_id = next((l["id"] for l in labels if l["name"] == label_name), None)

if not label_id:
    r = api("POST", "/labels", {"name": label_name, "color": label_color})
    label_id = r.get("id")

if label_id:
    api("POST", f"/issues/{issue_nr}/labels", {"labels": [label_id]})
    print(f"Label '{label_name}' (id={label_id}) auf Issue #{issue_nr} gesetzt")
else:
    print(f"Konnte Label '{label_name}' nicht erstellen", file=sys.stderr)
    sys.exit(1)
