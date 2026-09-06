"""Time one full planner call. usage: tools_planner_test.py [model]"""
import sys, time, json
from draftbot import engine, planner
model = sys.argv[1] if len(sys.argv) > 1 else "claude-fable-5-1"
pool, _ = engine.load_players()
drafted = {p["id"] for p in sorted(pool, key=lambda p: p["adp"])[:20]}
mine = [next(p for p in pool if p["name"] == "Ja'Marr Chase")]
rows, base, counts = engine.board(pool, drafted | {m["id"] for m in mine}, mine, 21, 28, top=25)
t = time.time()
p = planner.plan(rows, mine, 21, 28, ["Josh Allen (QB) -> Goat Rope"], model=model, timeout=300, my_picks=engine.my_picks(4))
ids = {r["id"]: r["name"] for r in rows}
print(f"{model}: {time.time()-t:.0f}s ${p.get('_cost') or 0:.2f} take={[ids.get(int(i), '?') for i in (p.get('take') or [])]}")
print("note:", p.get("note"))
