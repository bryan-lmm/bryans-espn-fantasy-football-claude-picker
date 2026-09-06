"""CLI: show the board for a hypothetical state. board.py --slot 4 --pick 4 [--drafted id,id] [--mine id,id]"""
import argparse, json
from draftbot import engine
ap = argparse.ArgumentParser()
ap.add_argument("--slot", type=int, default=4); ap.add_argument("--pick", type=int, default=None)
ap.add_argument("--drafted", default=""); ap.add_argument("--mine", default=""); ap.add_argument("--top", type=int, default=25)
a = ap.parse_args()
pool, _ = engine.load_players()
mine_ids = [int(x) for x in a.mine.split(",") if x]
drafted = set(int(x) for x in a.drafted.split(",") if x) | set(mine_ids)
picks = engine.my_picks(a.slot)
this_pick = a.pick or picks[0]
nxt = next((p for p in picks if p > this_pick), None)
roster = [p for p in pool if p["id"] in mine_ids]
rows, base, counts = engine.board(pool, drafted, roster, this_pick, nxt, a.top)
print("my picks:", picks)
print(engine.fmt(rows, base, counts, this_pick, nxt))
