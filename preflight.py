"""Go-live checklist. Run ~30 min before the draft: python preflight.py"""
import json, subprocess, time, sys
from draftbot.session import Ctx
from draftbot import espn, engine
from draftbot.config import DATA, LEAGUE_ID
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(("PASS" if cond else "FAIL"), label, detail)
# 1 fresh cookies from Chrome (you must be logged into ESPN in Chrome on this machine)
from pathlib import Path
if (Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies").exists() and not __import__("os").environ.get("SKIP_COOKIES"):
    r = subprocess.run([sys.executable, "tools_cookies.py"], capture_output=True, text=True); check("cookies refreshed from Chrome", r.returncode == 0, r.stdout.strip()[-80:])
else:
    check("cookies present (copied from another machine)", Path("secrets.json").exists() and Path("secrets_cookies.json").exists(), "SKIP_COOKIES / no Chrome here")
# 2 API auth + fresh pool (ADP / injury tags move on draft day)
ctx = Ctx(); lg = espn.league(ctx); check("league API auth", bool(lg.get("settings", {}).get("name")), lg.get("settings", {}).get("name"))
ds = lg["settings"]["draftSettings"]; check("draft settings", ds.get("type") == "SNAKE" and ds.get("timePerSelection") == 90, f"date={time.strftime('%Y-%m-%d %H:%M', time.localtime(ds['date']/1000))} slot order={ds.get('pickOrder')}")
pl = espn.players(ctx); byes = espn.pro_schedule(ctx)
for p in pl: p["bye"] = byes.get(p["proTeamId"])
(DATA / "players.json").write_text(json.dumps(pl, indent=1)); check("players refreshed", sum(1 for p in pl if p["proj"]) > 400, f"{len(pl)} players")
st = espn.draft_state(ctx); check("draft not started", not st["inProgress"] and not st["drafted"], str({k: v for k, v in st.items() if k != 'picks'}))
# 3 my slot from pickOrder (teamId order of round 1)
from draftbot.config import MY_TEAM_ID
slot = ds["pickOrder"].index(MY_TEAM_ID) + 1 if MY_TEAM_ID in ds["pickOrder"] else None; check("my slot (API; the bot re-detects it from the room)", slot is not None, f"slot={slot} picks={engine.my_picks(slot) if slot else None}")
# 4 overrides present and engine runs
pool, ov = engine.load_players(); check("overrides loaded", len(ov.get("boost", {})) > 20, f"{len(ov.get('boost', {}))} boosts, {len(ov.get('avoid', []))} avoids")
mp = engine.my_picks(slot or 4); rows, base, counts = engine.board(pool, set(), [], mp[0], mp[1], top=5); check("engine board", len(rows) == 5, [r["name"] for r in rows])
# 5 planner responds
t = time.time(); from draftbot.planner import claude_bin
r = subprocess.run([claude_bin(), "-p", "--model", "opus", "--output-format", "json", "Reply with exactly: READY"], capture_output=True, text=True, timeout=120)
check("planner (claude -p) responds", "READY" in r.stdout, f"{time.time()-t:.1f}s")
print("\nREMINDERS: close the ESPN draft room everywhere else (Chrome tabs, phone app). Only live.py's window may be connected.")
print("ALL GREEN" if ok else "SOMETHING FAILED")
