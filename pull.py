"""Snapshot league + player pool to data/. Idempotent."""
import json
from draftbot.session import Ctx
from draftbot import espn
from draftbot.config import DATA
ctx = Ctx()
lg = espn.league(ctx); (DATA / "league.json").write_text(json.dumps(lg, indent=1))
pl = espn.players(ctx); byes = espn.pro_schedule(ctx)
for p in pl: p["bye"] = byes.get(p["proTeamId"])
(DATA / "players.json").write_text(json.dumps(pl, indent=1))
print(f"league ok: {lg['settings']['name']}; players: {len(pl)} ({sum(1 for p in pl if p['proj'])} with proj)")
st = espn.draft_state(ctx); print("draft:", {k: v for k, v in st.items() if k != 'picks'}, "picks:", len(st["picks"]))
