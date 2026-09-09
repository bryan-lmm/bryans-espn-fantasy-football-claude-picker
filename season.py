"""In-season tools. usage: season.py roster | fa [--pos WR] [--week N] | lineup
Pulls live ESPN data (cookies), shows rest-of-season (ROS) + this-week projections, ownership, waiver status."""
import sys, json, argparse
from draftbot.session import Ctx
from draftbot.config import API, SEASON, POS, DATA, MY_TEAM_ID
from draftbot import engine
ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["roster", "fa", "lineup"]); ap.add_argument("--pos", default=None); ap.add_argument("--week", type=int, default=None); ap.add_argument("--limit", type=int, default=60); ap.add_argument("--sort", choices=["ros", "trending", "week"], default="ros")
a = ap.parse_args()
c = Ctx().request
lg = c.get(API + "?view=mTeam&view=mSettings&view=mRoster&view=mStatus").json()
week = a.week or lg.get("scoringPeriodId", 1)
byes = {int(k): v for k, v in json.loads((DATA / "pro_teams.json").read_text()).items()}  # abbrev map
teams_j = c.get(f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}?view=proTeamSchedules_wl").json()
bye_wk = {t["id"]: t.get("byeWeek") for t in teams_j["settings"]["proTeams"]}
opp = {}
for t in teams_j["settings"]["proTeams"]:
    for wk, games in (t.get("proGamesByScoringPeriod") or {}).items():
        if int(wk) == week and games:
            g = games[0]; o = g["awayProTeamId"] if g["homeProTeamId"] == t["id"] else g["homeProTeamId"]
            opp[t["id"]] = ("vs " if g["homeProTeamId"] == t["id"] else "@ ") + byes.get(o, str(o))
def stats(pl):
    ros = wk = last = None
    for s in pl.get("stats", []):
        if s.get("seasonId") != SEASON: continue
        if s.get("statSourceId") == 1 and s.get("scoringPeriodId") == 0: ros = s.get("appliedTotal")
        if s.get("statSourceId") == 1 and s.get("scoringPeriodId") == week: wk = s.get("appliedTotal")
    return ros, wk
ov = json.loads((DATA / "overrides.json").read_text()); boost = {int(k): v for k, v in ov["boost"].items()}
def row(pl, extra=""):
    ros, wk = stats(pl); own = pl.get("ownership") or {}
    b = boost.get(pl["id"], 0)
    return f"{pl['fullName']:<24} {POS.get(pl['defaultPositionId'], '?'):<3} {byes.get(pl.get('proTeamId'), '?'):<4} {opp.get(pl.get('proTeamId'), 'BYE?'):<7} ROS {ros or 0:6.1f}{'':1}{('+' if b>0 else '')+str(int(b)) if b else '':>4}  wk{week} {wk or 0:5.1f}  own {own.get('percentOwned', 0):5.1f}% ({own.get('percentChange', 0):+.1f})  {pl.get('injuryStatus','') or '':<12} {extra}"
if a.cmd in ("roster", "lineup"):
    me = next(t for t in lg["teams"] if t["id"] == MY_TEAM_ID)
    ids = [e["playerId"] for e in me["roster"]["entries"]]
    flt = {"players": {"filterIds": {"value": ids}, "limit": 50, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}, "filterStatsForTopScoringPeriodIds": {"value": 3, "additionalValue": [f"00{SEASON}", f"10{SEASON}", f"11{SEASON}{week}"]}}}
    pj = c.get(API + "?view=kona_player_info", headers={"X-Fantasy-Filter": json.dumps(flt)}).json()
    slot = {e["playerId"]: e["lineupSlotId"] for e in me["roster"]["entries"]}
    S = {0:"QB",2:"RB",4:"WR",6:"TE",16:"DST",17:"K",20:"BE",21:"IR",23:"FLEX"}
    print(f"OUR ROSTER  (week {week}; ROS = ESPN rest-of-season proj, +n = research boost)")
    for p in sorted(pj["players"], key=lambda p: (slot.get(p["id"], 99), -(stats(p["player"])[0] or 0))):
        print(f"  {S.get(slot.get(p['id']), '?'):<4} " + row(p["player"]))
else:
    slots = {"QB": [0], "RB": [2], "WR": [4], "TE": [6], "K": [17], "DST": [16]}
    flt = {"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "limit": a.limit, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}, "filterStatsForTopScoringPeriodIds": {"value": 3, "additionalValue": [f"00{SEASON}", f"10{SEASON}", f"11{SEASON}{week}"]}}}
    if a.pos: flt["players"]["filterSlotIds"] = {"value": slots[a.pos.upper()]}
    if a.sort == "trending": flt["players"]["sortPercChanged"] = {"sortPriority": 1, "sortAsc": False}; flt["players"].pop("sortPercOwned", None)
    pj = c.get(API + "?view=kona_player_info", headers={"X-Fantasy-Filter": json.dumps(flt)}).json()
    rows = [(p["player"], p.get("status"), p.get("onTeamId")) for p in pj["players"]]
    if a.sort == "ros": rows.sort(key=lambda r: -((stats(r[0])[0] or 0) + boost.get(r[0]["id"], 0)))
    elif a.sort == "week": rows.sort(key=lambda r: -(stats(r[0])[1] or 0))
    else: rows.sort(key=lambda r: -((r[0].get("ownership") or {}).get("percentChange", 0)))
    print(f"FREE AGENTS / WAIVERS  (week {week}; sorted by {a.sort})")
    for pl, status, _ in rows[:a.limit]:
        print("  " + row(pl, status or ""))
