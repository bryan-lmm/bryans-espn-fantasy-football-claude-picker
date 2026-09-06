"""Deterministic board: value over replacement + survival-to-next-pick + roster needs.
No LLM here. This is the ground truth the actuator falls back to."""
import json, math
from .config import DATA, SLOT

from .config import TEAMS, ROUNDS
# Replacement baseline = points of the Nth-ranked player at the position (12-team, 1 flex, 5 bench).
# Replacement = roughly the best player left on waivers after the draft (deep enough that bench-worthy
# players keep a positive VOR; otherwise K/DST with tiny positive VOR win late rounds by default).
BASELINE_RANK = {"QB": 15, "RB": 38, "WR": 42, "TE": 14, "K": 12, "DST": 12}
# Roster limits we will draft to (starters + sensible bench). Hard caps.
TARGET = {"QB": 2, "RB": 6, "WR": 6, "TE": 2, "K": 1, "DST": 1}
STARTERS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DST": 1, "FLEX": 1}
INJ_MULT = {"ACTIVE": 1.0, "PROBABLE": 1.0, "QUESTIONABLE": 0.97, "DOUBTFUL": 0.85, "OUT": 0.7, "INJURY_RESERVE": 0.5, "SUSPENSION": 0.8}

def load_players():
    pl = json.loads((DATA / "players.json").read_text())
    ov = json.loads((DATA / "overrides.json").read_text()) if (DATA / "overrides.json").exists() else {}
    rt = json.loads((DATA / "overrides_runtime.json").read_text()) if (DATA / "overrides_runtime.json").exists() else {}
    boosts = {int(k): v for k, v in ov.get("boost", {}).items()}
    for k, v in rt.get("boost", {}).items(): boosts[int(k)] = boosts.get(int(k), 0) + v      # planner's in-draft adjustments
    avoid = set(ov.get("avoid", [])) | set(rt.get("avoid", []))
    out = []
    for p in pl:
        if p["pos"] not in BASELINE_RANK or not p["proj"]:
            continue
        adj = p["proj"] * INJ_MULT.get(p.get("injury") or "ACTIVE", 1.0) + boosts.get(p["id"], 0)
        if p["id"] in avoid:
            adj -= 8   # research "overpriced at ADP" fade; injuries are handled via boosts
        p = dict(p); p["adj"] = adj
        out.append(p)
    return out, ov

def my_picks(slot, teams=TEAMS, rounds=ROUNDS):
    """Overall pick numbers for draft slot (1-based) in a snake."""
    picks = []
    for r in range(1, rounds + 1):
        pos = slot if r % 2 == 1 else teams + 1 - slot
        picks.append((r - 1) * teams + pos)
    return picks

# League-specific ADP correction (tune from your league's draft history; 1.0 = trust ESPN ADP as-is).
LEAGUE_ADP_MULT = {"QB": (0.78, 0.85), "TE": (0.9, 0.95)}
def league_adp(adp, pos):
    m = LEAGUE_ADP_MULT.get(pos)
    if not m or adp >= 900: return adp
    return adp * (m[0] if adp < 60 else m[1])

def team_need(pos, roster_counts, round_no):
    """How hungry an opposing team is for `pos` given what it has drafted (weights the picks between mine)."""
    have = roster_counts.get(pos, 0)
    if pos == "QB":  return 1.0 if have == 0 else (0.15 if round_no >= 9 else 0.03)
    if pos == "TE":  return 1.0 if have == 0 else (0.2 if round_no >= 9 else 0.05)
    if pos in ("K", "DST"): return 0.0 if have else (1.0 if round_no >= ROUNDS - 2 else 0.05)
    # RB / WR: everybody keeps taking them, but need modulates
    if have < STARTERS[pos]: return 1.15
    if have < STARTERS[pos] + 2: return 1.0
    return 0.7

def run_pressure(pos, recent_picks_pos):
    """Positional run detector: share of the last 8 picks at this position vs. a baseline."""
    if not recent_picks_pos: return 1.0
    base = {"QB": 0.12, "RB": 0.32, "WR": 0.36, "TE": 0.10, "K": 0.05, "DST": 0.05}[pos]
    share = sum(1 for q in recent_picks_pos[-8:] if q == pos) / min(8, len(recent_picks_pos))
    return max(0.6, min(1.8, 0.7 + share / max(base, 0.05) * 0.3))

def effective_gap(pos, this_pick, next_pick, opp_rosters=None, order=None, recent=None):
    """Picks between this_pick and next_pick, weighted by opponents' need at `pos` and any run in progress.
    opp_rosters: {teamId: {pos: count}}; order: {overall_pick: teamId} for the whole draft."""
    if not next_pick: return 0
    raw = next_pick - this_pick
    if not opp_rosters or not order: return raw
    round_no = (this_pick - 1) // TEAMS + 1
    w = 0.0
    for pk in range(this_pick + 1, next_pick):
        t = order.get(pk)
        w += team_need(pos, opp_rosters.get(t, {}), round_no) if t is not None else 1.0
    return w * run_pressure(pos, recent or [])

def survival(adp, at_pick, pos=None, gap_scale=1.0):
    """P(player still on board when pick `at_pick` comes up), normal around (league-adjusted) ADP.
    gap_scale stretches/compresses the wait: >1 means the teams in between are hungrier for this position."""
    if adp >= 900:  # undrafted in ESPN ADP => basically always available
        return 0.99
    adp = league_adp(adp, pos)
    sd = 2.0 + 0.11 * adp
    z = (at_pick - 0.5 - adp) / sd
    return 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))

def baselines(pool):
    """Replacement level from RAW projections (not boosted), so research boosts/fades never move the baseline."""
    base = {}
    for pos, n in BASELINE_RANK.items():
        ranked = sorted([p["proj"] for p in pool if p["pos"] == pos], reverse=True)
        base[pos] = ranked[min(n, len(ranked)) - 1] if ranked else 0
    return base

def roster_counts(roster):
    c = {k: 0 for k in TARGET}
    for p in roster: c[p["pos"]] = c.get(p["pos"], 0) + 1
    return c

REQUIRED = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DST": 1}   # slots that must be filled by the end of round 14

def need_multiplier(pos, counts, round_no):
    have = counts.get(pos, 0)
    if have >= TARGET[pos]:
        return 0.0
    # Endgame: if the rounds left are only enough to fill required empty slots, force those and nothing else.
    missing = [q for q, n in REQUIRED.items() if counts.get(q, 0) < n]
    rounds_left = ROUNDS - round_no + 1
    if missing and rounds_left <= len(missing):
        return 5.0 if pos in missing else 0.0
    if pos in ("K", "DST"):
        return 1.0 if round_no >= ROUNDS - 1 else 0.0    # last two rounds only, hard rule
    if pos == "QB":
        if have == 0:
            starters_open = (counts.get("RB", 0) < STARTERS["RB"]) or (counts.get("WR", 0) < STARTERS["WR"])
            return 0.8 if (round_no < 3 or starters_open) else 1.0
        return 0.0                                        # never a QB2: QB17-24 (240-267 proj) sit on waivers all year
    if pos == "TE":
        if have == 0: return 1.0 if round_no <= 3 else (1.25 if round_no <= 5 else (1.6 if round_no <= 7 else 2.2))   # TE1 is a starter: never drift to TE12
        return 0.0                                        # never a TE2
    # RB / WR share the flex: fill 2 starters each, then a 5th body, then depth
    rbwr = counts.get("RB", 0) + counts.get("WR", 0)
    other = "WR" if pos == "RB" else "RB"
    if have < STARTERS[pos]:
        # an open STARTER slot gets more urgent every round: a plateau WR2 at pick 69 (218) beats one at 93 (189) every week
        if round_no <= 3: return 1.0 if have > 0 else 1.05
        if round_no <= 5: return 1.2
        return 1.35
    if counts.get(other, 0) < STARTERS[other] and round_no >= 3:
        return 0.6                                             # no RB3/WR3 while the other position's starters are open
    if rbwr < 5: return 0.85
    if have < 4: return 0.65
    return 0.4

def board(pool, drafted_ids, my_roster, this_pick, next_pick, top=25, opp_rosters=None, order=None, recent=None):
    avail = [p for p in pool if p["id"] not in drafted_ids]
    base = baselines(pool)
    counts = roster_counts(my_roster)
    round_no = (this_pick - 1) // TEAMS + 1
    # opponent-aware effective wait per position: convert weighted gap back into a virtual "next pick"
    raw_gap = (next_pick - this_pick) if next_pick else 0
    eff_next = {}
    for pos in BASELINE_RANK:
        g = effective_gap(pos, this_pick, next_pick, opp_rosters, order, recent) if next_pick else 0
        eff_next[pos] = this_pick + g if next_pick else None
    rows = []
    for p in avail:
        vor = p["adj"] - base[p["pos"]]
        # Best expected VOR at same position if I wait until next_pick
        same = sorted([q for q in avail if q["pos"] == p["pos"] and q["id"] != p["id"]], key=lambda q: -q["adj"])
        exp_wait = 0.0; mass = 1.0
        for q in same[:12]:
            s = survival(q["adp"], eff_next[q["pos"]], q["pos"]) if next_pick else 0
            exp_wait += mass * s * (q["adj"] - base[p["pos"]]); mass *= (1 - s)
            if mass < 0.02: break
        exp_wait += mass * (same[12]["adj"] - base[p["pos"]] if len(same) > 12 else 0)
        surv_me = survival(p["adp"], eff_next[p["pos"]], p["pos"]) if next_pick else 0
        marginal = vor - exp_wait                       # what I gain by taking him NOW vs waiting at this position
        need = need_multiplier(p["pos"], counts, round_no)
        if need <= 0: continue                           # hard exclusion (caps, K/DST timing)
        score = need * (0.55 * vor + 0.45 * marginal) - 0.15 * max(0, p["adp"] - this_pick - 30)  # tiny reach penalty vs ADP
        rows.append({**p, "vor": round(vor, 1), "wait_vor": round(exp_wait, 1), "marginal": round(marginal, 1),
                     "surv_next": round(surv_me, 2), "need": need, "score": round(score, 1)})
    rows.sort(key=lambda r: -r["score"])
    board.eff_next = eff_next
    return rows[:top], base, counts

def fmt(rows, base, counts, this_pick, next_pick):
    lines = [f"pick {this_pick} (rd {(this_pick-1)//TEAMS+1}), next {next_pick}; roster {counts}; baselines {{{', '.join(f'{k}:{v:.0f}' for k,v in base.items())}}}",
             f"{'#':>3} {'name':<24} {'pos':<3} {'proj':>5} {'adp':>6} {'vor':>6} {'wait':>6} {'marg':>6} {'surv':>5} {'need':>4} {'score':>6}  inj"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i:>3} {r['name'][:24]:<24} {r['pos']:<3} {r['adj']:>5.0f} {r['adp']:>6.1f} {r['vor']:>6.1f} {r['wait_vor']:>6.1f} {r['marginal']:>6.1f} {r['surv_next']:>5.2f} {r['need']:>4.2f} {r['score']:>6.1f}  {(r.get('injury') or '')[:4]} bye{r.get('bye')}")
    return "\n".join(lines)
