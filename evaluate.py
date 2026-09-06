"""Score a finished draft: every team's optimal projected starting lineup (ESPN projections, league-scored) + bench value.
usage: evaluate.py data/picks_practice_<leagueId>.json  [--adj]   (--adj uses research-adjusted projections for OUR view)"""
import sys, json
from draftbot import engine
from draftbot.names import Matcher
from draftbot.config import DATA, MY_TEAM_NAME
SLOTS = [("QB", 1), ("RB", 2), ("WR", 2), ("TE", 1), ("K", 1), ("DST", 1)]
def lineup_points(players, key):
    pts = 0; used = set()
    for pos, n in SLOTS:
        pool = sorted([p for p in players if p["pos"] == pos], key=lambda p: -p[key])[:n]
        pts += sum(p[key] for p in pool); used |= {p["id"] for p in pool}
    flex = sorted([p for p in players if p["pos"] in ("RB", "WR", "TE") and p["id"] not in used], key=lambda p: -p[key])[:1]
    pts += sum(p[key] for p in flex); used |= {p["id"] for p in flex}
    bench = sorted([p[key] for p in players if p["id"] not in used], reverse=True)
    return pts, sum(bench[:3]) * 0.25, used
def main(path, use_adj=False):
    pool, _ = engine.load_players(); match = Matcher(pool)
    key = "adj" if use_adj else "proj"
    picks = json.loads(open(path).read())
    teams = {}
    for n, pk in sorted(((int(k), v) for k, v in picks.items())):
        p = match.find(pk["name"], pk["team"], pk["pos"])
        if p: teams.setdefault(pk["owner"], []).append(p)
    rows = []
    for owner, pl in teams.items():
        start, bench, used = lineup_points(pl, key)
        rows.append((start + bench, start, bench, owner, pl))
    rows.sort(reverse=True)
    print(f"{'rk':>2} {'total':>7} {'start':>7} {'bench':>6}  team")
    for i, (tot, st, be, owner, pl) in enumerate(rows, 1):
        flag = "  <== US" if owner.lower() == MY_TEAM_NAME.lower() else ""
        print(f"{i:>2} {tot:7.0f} {st:7.0f} {be:6.0f}  {owner}{flag}")
    me = next((r for r in rows if r[3].lower() == MY_TEAM_NAME.lower()), None)
    if me:
        print("\nOUR ROSTER:", ", ".join(f"{p['name']} ({p['pos']} {p[key]:.0f})" for p in me[4]))
        counts = engine.roster_counts(me[4]); print("counts:", counts)
    return rows
if __name__ == "__main__":
    main(sys.argv[1], "--adj" in sys.argv)
