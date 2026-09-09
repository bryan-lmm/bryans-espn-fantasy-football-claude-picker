"""Roster moves through ESPN's transactions endpoint (write host). usage:
   transact.py add <playerId> [--drop <playerId>]   [--dry-run]
   transact.py find "<name>"                            (look up ids)
ESPN's write API is undocumented; the payload shape below is the one the web client sends for a free-agent add/drop."""
import sys, json, argparse
from draftbot.session import Ctx, cookies
from draftbot.config import SEASON, LEAGUE_ID, MY_TEAM_ID, API
import requests
ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["add", "find", "drop", "lineup"]); ap.add_argument("arg"); ap.add_argument("--drop", type=int, default=None); ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--from-slot", type=int, default=None); ap.add_argument("--to-slot", type=int, default=None, help="lineup slots: QB 0, RB 2, WR 4, TE 6, DST 16, K 17, BE 20, IR 21, FLEX 23")
a = ap.parse_args()
c = Ctx()
if a.cmd == "find":
    flt = {"players": {"filterName": {"value": a.arg}, "limit": 10, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
    j = c.request.get(API + "?view=kona_player_info", headers={"X-Fantasy-Filter": json.dumps(flt)}).json()
    for p in j.get("players", []): print(p["id"], p["player"]["fullName"], p.get("status"), "team", p.get("onTeamId"))
    sys.exit()
lg = c.request.get(API + "?view=mStatus").json(); period = lg.get("scoringPeriodId", 1)
items = []
if a.cmd == "lineup":
    # swap two players' slots: arg = playerId moving INTO --to-slot; the occupant of that slot (if any) goes to --from-slot
    me = next(t for t in c.request.get(API + "?view=mRoster").json()["teams"] if t["id"] == MY_TEAM_ID)
    slot_of = {e["playerId"]: e["lineupSlotId"] for e in me["roster"]["entries"]}
    pid = int(a.arg); frm = a.from_slot if a.from_slot is not None else slot_of[pid]
    occupant = next((p for p, s_ in slot_of.items() if s_ == a.to_slot and p != pid), None)
    items.append({"playerId": pid, "type": "LINEUP", "fromLineupSlotId": frm, "toLineupSlotId": a.to_slot})
    if occupant is not None: items.append({"playerId": occupant, "type": "LINEUP", "fromLineupSlotId": a.to_slot, "toLineupSlotId": frm})
    payload = {"isLeagueManager": False, "teamId": MY_TEAM_ID, "type": "ROSTER", "memberId": cookies()["SWID"], "scoringPeriodId": period, "executionType": "EXECUTE", "items": items}
elif a.cmd == "add":
    items.append({"playerId": int(a.arg), "type": "ADD", "toTeamId": MY_TEAM_ID})
    if a.drop: items.append({"playerId": a.drop, "type": "DROP", "fromTeamId": MY_TEAM_ID})
elif a.cmd == "drop":
    items.append({"playerId": int(a.arg), "type": "DROP", "fromTeamId": MY_TEAM_ID})
if a.cmd != "lineup":
    payload = {"isLeagueManager": False, "teamId": MY_TEAM_ID, "type": "FREEAGENT", "memberId": cookies()["SWID"], "scoringPeriodId": period, "executionType": "EXECUTE", "items": items}
url = f"https://lm-api-writes.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}/transactions/"
print("POST", url); print(json.dumps(payload, indent=1))
if a.dry_run: print("(dry run, not sent)"); sys.exit()
s = c.request.s
r = s.post(url, json=payload, headers={"Content-Type": "application/json", "X-Fantasy-Source": "kona", "X-Fantasy-Platform": "kona-PROD"}, timeout=20)
print(r.status_code, r.text[:600])
