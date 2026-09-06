"""The draft loop. Engine picks; Playwright clicks; planner (claude -p) advises in the background between picks.
usage: live.py practice            -> league-specific practice draft vs auto teams (30s clock)
       live.py league              -> your real league's draft room
flags: --no-planner  --slot N  --team "Your Team Name"  --headless"""
import sys, time, json, threading, argparse, traceback, re
from pathlib import Path
from draftbot import engine
from draftbot.room import Room
from draftbot.names import Matcher
from draftbot.config import LEAGUE_ID, MY_TEAM_ID, MY_TEAM_NAME, DATA, SEASON, PLANNER_MODEL
def room_url_for(room):
    return f"https://fantasy.espn.com/football/draft?leagueId={LEAGUE_ID}&seasonId={SEASON}&teamId={MY_TEAM_ID}&memberId={room.swid}"
from draftbot import planner as planner_mod

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=["practice", "league"])
ap.add_argument("--slot", type=int, default=None, help="draft slot; practice mode uses it to start the room, league mode auto-detects (this is only a fallback)")
ap.add_argument("--team", default=None, help="your ESPN team name (default: config.json team_name)")
ap.add_argument("--no-planner", action="store_true"); ap.add_argument("--headless", action="store_true")
ap.add_argument("--planner-model", default=PLANNER_MODEL)
ap.add_argument("--rejoin", type=int, default=None, help="rejoin an existing practice room by its temp leagueId (crash-restart test)")
a = ap.parse_args()
a.team = a.team or MY_TEAM_NAME

LOG = DATA / f"live_{a.mode}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
def log(ev, **kw):
    kw.update(ev=ev, t=time.strftime("%H:%M:%S")); print(json.dumps(kw)[:300], flush=True)
    with LOG.open("a") as f: f.write(json.dumps(kw) + "\n")

(DATA / "overrides_runtime.json").unlink(missing_ok=True)      # planner notes from a previous draft never carry over
pool, _ = engine.load_players()
match = Matcher(pool)
lg = json.loads((DATA / "league.json").read_text())
def api_slot():
    """Round-1 slot for our teamId from the league skeleton (may be a placeholder if the order is randomized at draft start)."""
    try:
        order = lg["settings"]["draftSettings"]["pickOrder"]; return order.index(MY_TEAM_ID) + 1
    except Exception:
        return None
TEAM_NAMES = {t["id"]: (t.get("name") or "").strip() for t in lg.get("teams", [])}
NAME_TO_ID = {v.lower(): k for k, v in TEAM_NAMES.items()}
ORDER = {p["overallPickNumber"]: p["teamId"] for p in lg.get("draftDetail", {}).get("picks", [])}   # overall pick -> teamId

def opponent_state():
    """{teamId: {pos: count}} for every team from the pick feed, plus the positions of the last 8 picks."""
    rosters = {}; recent = []
    for n, pk in sorted(room.picks.items()):
        tid = NAME_TO_ID.get(pk["owner"].lower())
        pos = pk["pos"].replace("/", "")
        if tid is not None:
            rosters.setdefault(tid, {}); rosters[tid][pos] = rosters[tid].get(pos, 0) + 1
        recent.append(pos)
    return rosters, recent[-8:]
room = Room(headless=a.headless, my_team=a.team)
practice_slot = a.slot or api_slot() or 4
if a.mode == "practice" and a.rejoin:
    room.league_id = a.rejoin; ok = room.open_league_room(a.rejoin, MY_TEAM_ID)
elif a.mode == "practice":
    ok = room.start_practice(practice_slot)
else:
    room.page.goto(room_url_for(room)); ok = room.wait_ready(timeout=4 * 3600)
log("room", ready=ok, mode=a.mode, league=getattr(room, "league_id", LEAGUE_ID))
if not ok: sys.exit("room not ready")
room.settle()
# ---- which slot are we? The room is the source of truth (ESPN may randomize the order at draft start). ----
slot = None
for _ in range(10):
    slot = room.detect_slot(a.team)
    if slot: break
    time.sleep(1)
slot_source = "room"
if not slot:
    slot = a.slot or api_slot() or 4; slot_source = "flag/api fallback"
my_picks = engine.my_picks(slot)
log("slot", slot=slot, source=slot_source, my_picks=my_picks)
n_loaded = room.load_picks(DATA / f"picks_{a.mode}_{getattr(room, 'league_id', LEAGUE_ID)}.json")
try:
    n_back = room.backfill_history()
except Exception as e:
    n_back = f"failed: {e!s:.80}"
log("picks_restored", from_file=n_loaded, from_history_tab=n_back)

plan = {"take": [], "note": ""}; plan_lock = threading.Lock(); plan_thread = None
def run_planner(rows, roster, this_pick, next_pick, recent):
    global plan
    opp, _ = opponent_state()
    opp_named = {TEAM_NAMES.get(t, str(t)): c for t, c in opp.items()}
    p = planner_mod.plan(rows, roster, this_pick, next_pick, recent, model=a.planner_model, timeout=150, my_picks=my_picks,
                         opp_rosters=opp_named, eff_next={k: round(v, 1) for k, v in (getattr(engine.board, "eff_next", None) or {}).items() if v})
    p["for_pick"] = this_pick
    with plan_lock:
        plan = p
    planner_mod.apply_overrides(p)
    log("planner", ms=p.get("_ms"), cost=p.get("_cost"), take=p.get("take"), note=p.get("note"))

def drafted_sets():
    drafted, mine, unmatched = set(stale_drafted), [], []
    for n, pk in sorted(room.picks.items()):
        pl = match.find(pk["name"], pk["team"], pk["pos"])
        if pl:
            drafted.add(pl["id"])
            if pk["owner"].lower() == a.team.lower(): mine.append(pl)
        else:
            unmatched.append(pk["name"])
    return drafted, mine, unmatched

CONVICTION = json.loads((DATA / "conviction.json").read_text()) if (DATA / "conviction.json").exists() else {}

def conviction_order(this_pick, drafted):
    """Fable's hand-written board for the critical early ROUNDS (slot-independent): ordered ids for this round, minus drafted."""
    rnd = str((this_pick - 1) // engine.TEAMS + 1)
    lst = CONVICTION.get("by_round", {}).get(rnd) or []
    return [int(i) for i in lst if int(i) not in drafted]

def choose(drafted, mine, this_pick, next_pick):
    pool_now, _ = engine.load_players()          # picks up planner overrides
    opp, recent = opponent_state()
    rows, base, counts = engine.board(pool_now, drafted, mine, this_pick, next_pick, top=12, opp_rosters=opp, order=ORDER, recent=recent)
    order = []
    with plan_lock: take = list(plan.get("take") or []) if plan.get("for_pick") == this_pick else []   # never apply a stale plan
    # planner's list first (only if still available and in the engine's top 12), then engine order
    top_ids = [r["id"] for r in rows]
    for pid in take:
        if pid in top_ids and pid not in drafted and pid not in order: order.append(pid)
    for r in rows:
        if r["id"] not in order: order.append(r["id"])
    # Fable's conviction board outranks everything at the picks it covers (players must still be available)
    conv = conviction_order(this_pick, drafted)
    if conv and this_pick <= 3 * engine.TEAMS:
        # position-balance guard: through round 3 never let the conviction list hand us a 3rd player at one position
        cap = CONVICTION.get("max_same_pos_through_round3", 2); have = engine.roster_counts(mine)
        byid_pool0 = {p["id"]: p for p in pool_now}
        conv = [i for i in conv if have.get(byid_pool0.get(i, {}).get("pos", ""), 0) < cap]
    if conv:
        byid_pool = {p["id"]: p for p in pool_now}
        rows_by_id = {r["id"]: r for r in rows}
        front = [rows_by_id.get(i) or {**byid_pool[i], "score": 999, "vor": 0, "marginal": 0, "surv_next": 0, "need": 1} for i in conv if i in byid_pool]
        order = [c["id"] for c in front] + [i for i in order if i not in conv]
        rows = front + [r for r in rows if r["id"] not in conv]
    byid = {r["id"]: r for r in rows}
    return [byid[i] for i in order], rows, counts

last_planned_at = -1; last_state_line = None; done = False; gone_since = None; queued_for = None; stale_drafted = set()
while not done:
    try:
        s = room.state()
        # ---- connection health ----
        if s["disconnected"]:
            log("disconnected", modal=s["modal"]); log("recover", result=room.recover("modal")); continue
        if s["room_gone"]:
            gone_since = gone_since or time.time()
            if time.time() - gone_since > 6:
                log("recover", result=room.recover(f"clock={s['clock']} for 6s")); gone_since = None
            time.sleep(1); continue
        gone_since = None
        if s["on_autopick"]:
            room.disable_autopick(); log("autopick_disabled")
        drafted, mine, unmatched = drafted_sets()
        otc = s["otc_pick"] or (len(drafted) + 1)
        # ESPN's "ON THE CLOCK: PICK N" can lag a pick behind; the team name is the reliable signal.
        team_says_me = (s["otc_team"] or "").strip().lower() == a.team.strip().lower()
        s["my_turn"] = team_says_me or (otc in my_picks and s["draftBtns"] > 0 and not s["on_autopick"])
        if s["my_turn"] and otc not in my_picks:
            otc = next((p for p in my_picks if p >= otc), otc)      # snap the lagging pick number to my slot
        nxt = next((p for p in my_picks if p > otc), None)
        line = f"otc={otc} clock={s['clock']} my_turn={s['my_turn']} drafted={len(drafted)}"
        if line != last_state_line: log("state", otc=otc, clock=s["clock"], my_turn=s["my_turn"], drafted=len(drafted), unmatched=unmatched[-3:]); last_state_line = line
        if len(drafted) >= 168 or "complete" in (s["body0"] or "").lower():
            log("draft_complete"); done = True; break

        my_next = next((p for p in my_picks if p >= otc), None)
        if my_next is None: done = True; break

        # ---- off-clock: run the planner once per window when we're 2-6 picks out (practice: any gap) ----
        if not a.no_planner and not s["my_turn"] and (my_next - otc) <= 9 and last_planned_at != my_next and (plan_thread is None or not plan_thread.is_alive()):
            cands, rows, counts = choose(drafted, mine, my_next, next((p for p in my_picks if p > my_next), None))
            recent = [f"{room.picks[k]['name']} ({room.picks[k]['pos']}) -> {room.picks[k]['owner']}" for k in sorted(room.picks)[-12:]]
            plan_thread = threading.Thread(target=run_planner, args=(rows, mine, my_next, next((p for p in my_picks if p > my_next), None), recent), daemon=True)
            plan_thread.start(); last_planned_at = my_next
            log("planner_started", for_pick=my_next, engine_top=[r["name"] for r in rows[:5]])

        # ---- queue fallback: 1-2 picks out, park the engine's top 3 in ESPN's queue so a timeout drafts OUR guy ----
        if not s["my_turn"] and 0 < (my_next - otc) <= 2 and queued_for != my_next:
            try:
                cands, rows, counts = choose(drafted, mine, my_next, next((p for p in my_picks if p > my_next), None))
                qd = [c["name"] for c in cands[:3] if room.queue(c["name"], c["pos"])]
                room.clear_search(); queued_for = my_next; log("queued", for_pick=my_next, names=qd)
            except Exception as e:
                log("queue_failed", err=str(e)[:120])

        # ---- on clock ----
        if s["my_turn"]:
            t0 = time.time()
            if s["on_autopick"] or room.page.locator("button.autopick-btn", has_text=re.compile("disable", re.I)).count():
                room.disable_autopick(); log("autopick_disabled_on_turn"); time.sleep(0.5)
            cands, rows, counts = choose(drafted, mine, otc, nxt)
            log("on_clock", pick=otc, clock=s["clock"], roster=counts, eff_next={k: round(v, 1) for k, v in (engine.board.eff_next or {}).items() if v}, candidates=[(c["name"], c["pos"], c["score"]) for c in cands[:5]], plan_note=plan.get("note") if plan.get("for_pick") == otc else None,
                ui={k: s.get(k) for k in ("autopickBtn", "draftBtns", "rowBtns", "modal", "discText", "otcTeam")})
            picked = None
            for c in cands[:8]:
                if room.draft(c["name"], c["pos"]):
                    picked = c; break
                log("draft_click_failed", name=c["name"], why=getattr(room, "last_error", None))
                if room.last_error == "already drafted":
                    stale_drafted.add(c["id"])          # our feed missed this pick; exclude and re-sync after the turn
                try: room.screenshot(DATA / f"fail_{otc}_{c['name'].split()[-1]}.png")
                except Exception: pass
            room.clear_search()
            log("picked", name=picked["name"] if picked else None, pos=picked["pos"] if picked else None, ms=int((time.time() - t0) * 1000))
            # wait until the pick registers (otc advances) so we don't double-fire
            for _ in range(40):
                time.sleep(0.25); s2 = room.state()
                if (s2["otc_pick"] or 0) > otc or not s2["my_turn"]: break
            with plan_lock: plan = {"take": [], "note": ""}
            if stale_drafted:
                try: log("resync_history", added=room.backfill_history())
                except Exception as e: log("resync_failed", err=str(e)[:100])
        time.sleep(0.4)
    except KeyboardInterrupt:
        break
    except Exception as e:
        log("error", err=str(e)[:200]); traceback.print_exc(); time.sleep(1)

drafted, mine, unmatched = drafted_sets()
log("final_roster", roster=[(p["name"], p["pos"], p["adj"], p["adp"]) for p in mine], unmatched=unmatched)
room.screenshot(DATA / f"final_{a.mode}.png"); time.sleep(2); room.close()
