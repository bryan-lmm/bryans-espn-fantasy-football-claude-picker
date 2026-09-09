"""Weekly roster optimizer: starters by matchup-adjusted weekly projection, bench audit vs the free-agent pool, adds/drops.
usage: weekly.py [--week N] [--json]
Per player: ESPN weekly projection x Vegas game-environment multiplier (team implied total vs league avg) + research boost/17
+ injury discount. Starters = best lineup from that. Bench = keep if (ROS+boost) beats the best free agent at that position,
or if the player is a handcuff to one of our starters. Free agents that beat a bench spot become add/drop recommendations."""
import json, argparse, requests
from draftbot.session import Ctx
from draftbot.config import API, SEASON, DATA, MY_TEAM_ID, POS
ap = argparse.ArgumentParser(); ap.add_argument("--week", type=int, default=None); ap.add_argument("--json", action="store_true"); a = ap.parse_args()
c = Ctx().request
lg = c.get(API + "?view=mTeam&view=mRoster&view=mStatus").json(); week = a.week or lg.get("scoringPeriodId", 1)
abbr = {int(k): v for k, v in json.loads((DATA / "pro_teams.json").read_text()).items()}
ov = json.loads((DATA / "overrides.json").read_text()); boost = {int(k): v for k, v in ov["boost"].items()}
INJ = {"ACTIVE": 1.0, "PROBABLE": 1.0, "QUESTIONABLE": 0.9, "DOUBTFUL": 0.4, "OUT": 0.0, "INJURY_RESERVE": 0.0, "SUSPENSION": 0.0}
# --- Vegas game environment ---
sb = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week={week}&seasontype=2&dates={SEASON}", timeout=20).json()
env = {}
for ev in sb.get("events", []):
    comp = ev["competitions"][0]; t = {x["homeAway"]: x for x in comp["competitors"]}
    odds = (comp.get("odds") or [{}])[0]; ou = odds.get("overUnder"); spread = odds.get("spread")
    home, away = t["home"]["team"]["abbreviation"], t["away"]["team"]["abbreviation"]
    ht = at = None
    if ou is not None and spread is not None: ht, at = (ou - spread) / 2, (ou + spread) / 2
    env[home] = {"opp": away, "home": True, "implied": ht, "opp_implied": at, "ou": ou}
    env[away] = {"opp": home, "home": False, "implied": at, "opp_implied": ht, "ou": ou}
env["WAS"] = env.get("WSH", env.get("WAS", {}))
AVG_IMPLIED = 22.5
def game(pl):
    return env.get(abbr.get(pl.get("proTeamId"), "?"), {})
def wk_proj(pl):
    return next((s["appliedTotal"] for s in pl.get("stats", []) if s.get("statSourceId") == 1 and s.get("scoringPeriodId") == week and s.get("seasonId") == SEASON), 0) or 0
def ros_proj(pl):
    return next((s["appliedTotal"] for s in pl.get("stats", []) if s.get("statSourceId") == 1 and s.get("scoringPeriodId") == 0 and s.get("seasonId") == SEASON), 0) or 0
def score_week(pl):
    g = game(pl); base = wk_proj(pl); pos = POS.get(pl["defaultPositionId"], "?")
    if not g: return 0.0, "BYE"
    if pos == "DST":
        oi = g.get("opp_implied"); mult = 1.0 if oi is None else max(0.6, min(1.5, 1 + (AVG_IMPLIED - oi) / AVG_IMPLIED * 1.2))
    else:
        ti = g.get("implied"); mult = 1.0 if ti is None else max(0.85, min(1.15, 1 + (ti - AVG_IMPLIED) / AVG_IMPLIED * 0.6))
    inj = INJ.get(pl.get("injuryStatus") or "ACTIVE", 1.0)
    val = (base * mult + boost.get(pl["id"], 0) / 17.0) * inj
    tag = f"{'vs' if g.get('home') else '@'} {g.get('opp')} impl {g.get('implied'):.1f}" if pos != "DST" else f"{'vs' if g.get('home') else '@'} {g.get('opp')} opp {g.get('opp_implied'):.1f}"
    return val, tag
def fetch(flt):
    return c.get(API + "?view=kona_player_info", headers={"X-Fantasy-Filter": json.dumps(flt)}).json().get("players", [])
stats_filter = {"value": 3, "additionalValue": [f"00{SEASON}", f"10{SEASON}", f"11{SEASON}{week}"]}
me = next(t for t in lg["teams"] if t["id"] == MY_TEAM_ID)
slot_of = {e["playerId"]: e["lineupSlotId"] for e in me["roster"]["entries"]}
roster = [p["player"] for p in fetch({"players": {"filterIds": {"value": list(slot_of)}, "limit": 50, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}, "filterStatsForTopScoringPeriodIds": stats_filter}})]
fa = [p["player"] for p in fetch({"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "limit": 150, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}, "filterStatsForTopScoringPeriodIds": stats_filter}})]
# --- starters ---
SLOTS = [("QB", ["QB"], 1), ("RB", ["RB"], 2), ("WR", ["WR"], 2), ("TE", ["TE"], 1), ("FLEX", ["RB", "WR", "TE"], 1), ("K", ["K"], 1), ("DST", ["DST"], 1)]
scored = {pl["id"]: score_week(pl) for pl in roster}
pos_of = {pl["id"]: POS.get(pl["defaultPositionId"], "?") for pl in roster}
used = set(); lineup = []
for slot, elig, n in SLOTS:
    cands = sorted([pl for pl in roster if pos_of[pl["id"]] in elig and pl["id"] not in used], key=lambda pl: -scored[pl["id"]][0])[:n]
    for pl in cands: used.add(pl["id"]); lineup.append((slot, pl))
S = {0:"QB",2:"RB",4:"WR",6:"TE",16:"DST",17:"K",20:"BE",21:"IR",23:"FLEX"}
print(f"=== WEEK {week} STARTERS (matchup-adjusted; current slot in brackets) ===")
for slot, pl in lineup:
    v, tag = scored[pl["id"]]; cur = S.get(slot_of.get(pl["id"]), "?"); flag = "" if cur in (slot, "FLEX" if slot in ("RB","WR","TE") else slot) or (slot == "FLEX" and cur in ("RB","WR","TE")) else "  <-- CHANGE"
    print(f"  {slot:<4} {pl['fullName']:<22} {v:5.1f}  {tag:<22} ESPN wk {wk_proj(pl):4.1f}  [{cur}]{flag}")
bench = [pl for pl in roster if pl["id"] not in used]
print("  bench:", ", ".join(f"{pl['fullName'].split()[-1]} {scored[pl['id']][0]:.1f}" for pl in sorted(bench, key=lambda pl: -scored[pl['id']][0])))
# --- bench audit vs free agents ---
print(f"\n=== BENCH AUDIT (ROS + boost vs best free agent at position) ===")
fa_by_pos = {}
for pl in fa:
    p = POS.get(pl["defaultPositionId"], "?"); fa_by_pos.setdefault(p, []).append(pl)
def ros_adj(pl): return (ros_proj(pl) + boost.get(pl["id"], 0)) * (0.5 if (pl.get("injuryStatus") in ("INJURY_RESERVE", "OUT")) else 1.0)
for p in fa_by_pos: fa_by_pos[p].sort(key=lambda pl: -ros_adj(pl))
handcuff_ids = set(json.loads((DATA / "handcuffs.json").read_text()).get("ids", [])) if (DATA / "handcuffs.json").exists() else set()
for pl in sorted(bench, key=lambda pl: ros_adj(pl)):
    p = pos_of[pl["id"]]; best = fa_by_pos.get(p, [None])[0]
    note = "HANDCUFF (keep)" if pl["id"] in handcuff_ids else ""
    verdict = "keep" if not best or ros_adj(pl) >= ros_adj(best) or note else f"SWAP for {best['fullName']} ({ros_adj(best):.0f})"
    print(f"  {pl['fullName']:<22} {p:<3} ROS+ {ros_adj(pl):5.0f}  wk {scored[pl['id']][0]:4.1f}  own chg {(pl.get('ownership') or {}).get('percentChange', 0):+.1f}  best FA {p}: {best['fullName'] if best else '-'} {ros_adj(best) if best else 0:.0f}  -> {verdict} {note}")
print(f"\n=== TOP FREE AGENTS by ROS+boost (stash value) and by this-week matchup ===")
for p in ("RB", "WR", "TE", "QB"):
    top = fa_by_pos.get(p, [])[:5]
    print(f"  {p}: " + " | ".join(f"{pl['fullName']} {ros_adj(pl):.0f} (wk {score_week(pl)[0]:.1f}, chg {(pl.get('ownership') or {}).get('percentChange', 0):+.1f})" for pl in top))
if a.json:
    out = {"week": week, "starters": [(s, pl["fullName"], round(scored[pl["id"]][0], 1), scored[pl["id"]][1]) for s, pl in lineup],
           "bench": [(pl["fullName"], pos_of[pl["id"]], round(ros_adj(pl)), round(scored[pl["id"]][0], 1)) for pl in bench],
           "top_fa": {p: [(pl["fullName"], round(ros_adj(pl)), round(score_week(pl)[0], 1)) for pl in fa_by_pos.get(p, [])[:6]] for p in ("RB", "WR", "TE", "QB", "DST")}}
    (DATA / f"weekly_wk{week}.json").write_text(json.dumps(out, indent=1))
