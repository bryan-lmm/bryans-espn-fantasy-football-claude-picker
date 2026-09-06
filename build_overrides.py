"""Rebuild data/overrides.json deterministically from the research files + hand-picked conviction boosts. Run any time."""
import json
from draftbot.config import DATA
pl = {p["name"]: p for p in json.load(open(DATA / "players.json"))}; low = {k.lower(): v for k, v in pl.items()}
ID = lambda n: pl[n]["id"]
boost, avoid = {}, set()
def add(pid, b): boost[int(pid)] = boost.get(int(pid), 0) + b
for o in json.load(open(DATA / "research_injuries.json")):
    if o.get("id") and o.get("boost"): add(o["id"], int(o["boost"]))
strat = json.load(open(DATA / "research_strategy.json"))
for k, v in (strat.get("boost") or {}).items(): add(k, max(-30, min(30, int(v))))
avoid |= {int(x) for x in strat.get("avoid", [])}
for n, b in [("Drake London", 10), ("Chase Brown", 10), ("Nico Collins", 8), ("Trey McBride", 6), ("Kenneth Walker III", 6), ("Javonte Williams", 6), ("DeVonta Smith", 10), ("Zay Flowers", 10), ("Tetairoa McMillan", 8), ("Drake Maye", 12), ("Jayden Daniels", 6), ("Tyler Warren", 6), ("Bijan Robinson", 6), ("Jaxon Smith-Njigba", 4),
             ("Breece Hall", -12), ("Omarion Hampton", -10), ("Rashee Rice", -8), ("Malik Nabers", -6), ("Cam Skattebo", -16), ("Quinshon Judkins", 6), ("De'Von Achane", -10), ("Puka Nacua", -6), ("Christian McCaffrey", -8), ("Chris Olave", -6), ("George Pickens", -4)]:
    add(ID(n), b)
sl = json.load(open(DATA / "research_sleepers.json"))
for grp, cap in (("sleepers", 15), ("late_qb", 10), ("late_te", 10)):
    for s in sl.get(grp, []):
        pid = s.get("id") or (low.get((s.get("name") or "").lower()) or {}).get("id")
        if pid: add(pid, max(3, min(cap, int(s.get("boost") or 8))))
for n in sl.get("dst", []):
    p = low.get(f"{n} d/st".lower());  p and add(p["id"], 6)
for n in sl.get("k", []):
    p = low.get(n.lower());  p and add(p["id"], 6)
boost = {str(k): max(-60, min(40, v)) for k, v in boost.items() if v}
json.dump({"boost": boost, "avoid": sorted(avoid), "source": "build_overrides.py from research_* + conviction, 2026-09-05"}, open(DATA / "overrides.json", "w"), indent=1)
print(f"overrides rebuilt: {len(boost)} boosts, {len(avoid)} avoids")
