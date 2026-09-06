"""Compare rosters mid-draft: analyze.py "Team A" "Team B" ; ranks every team by projected optimal starters so far."""
import sys, json
from draftbot import engine
from draftbot.names import Matcher
from draftbot.config import DATA, LEAGUE_ID
import evaluate
pool, ov = engine.load_players(); m = Matcher(pool)
p = json.load(open(DATA / f"picks_league_{LEAGUE_ID}.json"))
teams = {}
for k, v in sorted(p.items(), key=lambda x: int(x[0])):
    x = m.find(v["name"], v["team"], v["pos"])
    if x: teams.setdefault(v["owner"], []).append((int(k), x))
print("total picks:", len(p))
for owner in sys.argv[1:]:
    pl = teams.get(owner, [])
    print(f"\n=== {owner} ===")
    for n, x in pl:
        print(f"  #{n:>3} {x['name']:<24} {x['pos']:<3} proj {x['proj']:>5.0f}  adj {x['adj']:>5.0f}  adp {x['adp']:>5.1f}  {str(x.get('injury') or '')[:4]}")
    for key in ("proj", "adj"):
        st, be, used = evaluate.lineup_points([x for _, x in pl], key)
        print(f"  starters({key}) = {st:.0f}   bench {be:.0f}   counts {engine.roster_counts([x for _, x in pl])}")
rows = []
for owner, pl in teams.items():
    st, _, _ = evaluate.lineup_points([x for _, x in pl], "proj"); sta, _, _ = evaluate.lineup_points([x for _, x in pl], "adj")
    rows.append((st, sta, owner, len(pl)))
rows.sort(reverse=True)
print("\nALL TEAMS by projected optimal starters so far (raw / research-adjusted / picks):")
for i, (st, sta, o, n) in enumerate(rows, 1): print(f"  {i:>2} {st:6.0f} {sta:6.0f} {n:>2}  {o}")
