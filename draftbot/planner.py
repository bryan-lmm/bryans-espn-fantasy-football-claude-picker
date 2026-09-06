"""Off-clock planner: asks a strong model (headless `claude -p`) for strategic adjustments
given the engine's board. Output is JSON; the engine stays ground truth. Hard timeout."""
import json, subprocess, time, shutil, os
from pathlib import Path
from .config import DATA

def claude_bin():
    """The claude CLI: PATH first, then ~/.local/bin (the mini's non-login shells don't have it on PATH)."""
    return os.environ.get("CLAUDE_BIN") or shutil.which("claude") or str(Path.home() / ".local/bin/claude")

SYSTEM = """You are the strategist for an ESPN fantasy football snake draft (league settings are in the brief below). A deterministic engine already ranks
players by value-over-replacement and survival-to-next-pick. Your job is judgment the engine lacks:
positional runs (use opponent_rosters_by_position: a team with a QB won't take one; count who still needs each position
before my next pick), roster construction, bye clustering (avoid 3+ starters on one bye), the snake turn (picks 21+28,
45+52, 69+76... come as PAIRS with a 17-pick gap after), and reading the other 11 teams' needs. Trust the engine's 'adj'
projections (they already include today's injury research and expert fades); your edge is sequencing. Be decisive. Output ONLY JSON:
{"take": [<playerId in priority order, top 6, all should be acceptable picks>],
 "if_gone": {"<playerId>": "<one-line why the next one is fine>"},
 "boost": {"<playerId>": <+/- points to add to season projection, max +-25>},
 "avoid": [<playerIds to avoid at this price>],
 "note": "<two sentences max: the plan for this pick and the next>"}"""

def plan(board_rows, roster, this_pick, next_pick, recent_picks, model="opus", timeout=75, my_picks=None, opp_rosters=None, eff_next=None):
    payload = {
        "this_pick": this_pick, "next_pick": next_pick, "my_remaining_picks_after_this": [p for p in (my_picks or []) if p > this_pick],
        "roster_targets": {"QB": 1, "RB": "4-6", "WR": "4-6", "TE": 1, "K": "1 (round 13-14 only)", "DST": "1 (round 13-14 only)", "bench": 5},
        "my_roster": [{"id": p["id"], "name": p["name"], "pos": p["pos"], "bye": p.get("bye")} for p in roster],
        "last_12_picks": recent_picks,
        "opponent_rosters_by_position": opp_rosters or {},
        "engine_virtual_next_pick_by_position": eff_next or {},   # > my real next pick = teams between us are hungry for that position
        "engine_board": [{k: r[k] for k in ("id", "name", "pos", "adj", "adp", "vor", "marginal", "surv_next", "score", "injury", "bye")} for r in board_rows[:25]],
    }
    brief = (DATA / "planner_brief.txt").read_text() if (DATA / "planner_brief.txt").exists() else ""
    prompt = SYSTEM + "\n" + brief + "\n\nSTATE:\n" + json.dumps(payload)
    t0 = time.time()
    try:
        out = subprocess.run([claude_bin(), "-p", "--model", model, "--output-format", "json", prompt],
                             capture_output=True, text=True, timeout=timeout)
        res = json.loads(out.stdout)
        text = res.get("result", "")
        text = text[text.find("{"): text.rfind("}") + 1]
        p = json.loads(text)
        p["_ms"] = int((time.time() - t0) * 1000); p["_cost"] = res.get("total_cost_usd")
        return p
    except subprocess.TimeoutExpired as e:
        return {"take": [], "boost": {}, "avoid": [], "note": f"planner timed out ({model})", "_ms": int((time.time() - t0) * 1000)}
    except Exception as e:  # model/CLI error (not a timeout): one retry on Opus with the time left, else engine alone
        if model != "opus" and time.time() - t0 < timeout * 0.5:
            return plan(board_rows, roster, this_pick, next_pick, recent_picks, model="opus", timeout=max(30, int(timeout - (time.time() - t0))), my_picks=my_picks, opp_rosters=opp_rosters, eff_next=eff_next)
        return {"take": [], "boost": {}, "avoid": [], "note": f"planner failed ({model}): {e!s:.100}", "_ms": int((time.time() - t0) * 1000)}

def apply_overrides(p):
    """Planner boosts/avoids go to data/overrides_runtime.json (reset at the start of every draft; never into the research file)."""
    f = DATA / "overrides_runtime.json"
    ov = json.loads(f.read_text()) if f.exists() else {"boost": {}, "avoid": []}
    for k, v in (p.get("boost") or {}).items():
        ov["boost"][str(k)] = max(-25, min(25, float(v)))
    ov["avoid"] = sorted(set(ov.get("avoid", [])) | set(int(x) for x in p.get("avoid", [])))
    f.write_text(json.dumps(ov, indent=1))
    return ov
