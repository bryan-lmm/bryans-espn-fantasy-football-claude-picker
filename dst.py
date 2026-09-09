"""Weekly D/ST streaming ranker. usage: dst.py [--week N]
Inputs per defense: opponent implied total (Vegas, via ESPN's public scoreboard), spread, O/U, home/away, weather/dome,
ESPN weekly projection, ESPN ROS projection (as a defense-quality prior), availability in our league.
Score = weighted blend; the opponent's implied total is the strongest single predictor of D/ST points."""
import json, argparse, requests
from draftbot.session import Ctx
from draftbot.config import API, SEASON, DATA, MY_TEAM_ID
ap = argparse.ArgumentParser(); ap.add_argument("--week", type=int, default=None); a = ap.parse_args()
c = Ctx().request
lg = c.get(API + "?view=mStatus").json(); week = a.week or lg.get("scoringPeriodId", 1)
abbr = {int(k): v for k, v in json.loads((DATA / "pro_teams.json").read_text()).items()}
ALIAS = {"WSH": "WAS", "LAR": "LAR"}
sb = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week={week}&seasontype=2&dates={SEASON}", timeout=20).json()
games = {}
for ev in sb.get("events", []):
    comp = ev["competitions"][0]; t = {x["homeAway"]: x for x in comp["competitors"]}
    odds = (comp.get("odds") or [{}])[0]; ou = odds.get("overUnder"); spread = odds.get("spread")
    home, away = t["home"]["team"]["abbreviation"], t["away"]["team"]["abbreviation"]
    ht = at = None
    if ou is not None and spread is not None: ht, at = (ou - spread) / 2, (ou + spread) / 2
    wx = comp.get("weather") or {}; indoor = comp.get("venue", {}).get("indoor")
    games[home] = {"opp": away, "home": True, "opp_implied": at, "own_implied": ht, "ou": ou, "line": odds.get("details"), "wx": wx.get("displayValue") or ("dome" if indoor else "?"), "temp": wx.get("temperature"), "date": ev.get("date", "")[:10]}
    games[away] = {"opp": home, "home": False, "opp_implied": ht, "own_implied": at, "ou": ou, "line": odds.get("details"), "wx": wx.get("displayValue") or ("dome" if indoor else "?"), "temp": wx.get("temperature"), "date": ev.get("date", "")[:10]}
flt = {"players": {"filterSlotIds": {"value": [16]}, "limit": 40, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}, "filterStatsForTopScoringPeriodIds": {"value": 2, "additionalValue": [f"10{SEASON}", f"11{SEASON}{week}"]}}}
pj = c.get(API + "?view=kona_player_info", headers={"X-Fantasy-Filter": json.dumps(flt)}).json()
rows = []
for p in pj["players"]:
    pl = p["player"]; team = abbr.get(pl.get("proTeamId"), "?"); key = {"WAS": "WSH"}.get(team, team)
    g = games.get(key) or games.get(team) or {}
    ros = next((s["appliedTotal"] for s in pl.get("stats", []) if s.get("statSourceId") == 1 and s.get("scoringPeriodId") == 0), 0)
    wk = next((s["appliedTotal"] for s in pl.get("stats", []) if s.get("statSourceId") == 1 and s.get("scoringPeriodId") == week), 0)
    oi = g.get("opp_implied")
    # composite: opponent implied total dominates (each point of implied total ~ -0.35 D/ST pts), home +0.5, ESPN week proj as tie-breaker, ROS as a small quality prior
    score = (0 if oi is None else (24 - oi) * 0.35) + (0.5 if g.get("home") else 0) + 0.5 * (wk or 0) + 0.01 * (ros or 0)
    rows.append((score, team, g, ros, wk, p.get("status"), p.get("onTeamId"), (pl.get("ownership") or {}).get("percentOwned", 0)))
rows.sort(reverse=True)
print(f"D/ST WEEK {week} RANKER  (score = 0.35*(24 - opp implied) + home 0.5 + 0.5*ESPN wk proj + 0.01*ROS)")
print(f"{'score':>5} {'D/ST':<5} {'opp':<7} {'line':<10} {'O/U':>5} {'opp impl':>8} {'wx':<14} {'wk':>4} {'ROS':>5} {'own':>5}  status")
for score, team, g, ros, wk, status, on, own in rows[:20]:
    opp = ("vs " if g.get("home") else "@ ") + g.get("opp", "?") if g else "BYE"
    mine = "  <== OURS" if on == MY_TEAM_ID else ""
    print(f"{score:5.1f} {team:<5} {opp:<7} {str(g.get('line') or '?'):<10} {str(g.get('ou') or '?'):>5} {('%.1f' % g['opp_implied']) if g.get('opp_implied') is not None else '?':>8} {str(g.get('wx') or '?')[:14]:<14} {wk:4.1f} {ros:5.0f} {own:4.0f}%  {status or ''}{mine}")
