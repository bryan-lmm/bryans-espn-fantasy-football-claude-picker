# Bryan's ESPN Fantasy Football Claude Picker

An autonomous ESPN fantasy football draft bot. A deterministic value-over-replacement engine picks, Playwright clicks in
ESPN's draft room, and Claude (via the `claude` CLI) advises between picks. Built and battle-tested in one day for a
12-team full-PPR league; it drafted a complete 14-round roster live, unattended, from a headless Mac mini.

**What it does**
- Reads your league (settings, scoring, projections, ADP, 10 years of draft history) from ESPN's undocumented v3 API using
  your own browser session cookies. Projections come back already scored to your league's rules.
- Builds a board: value over replacement (raw-projection baselines), survival-to-your-next-pick from ADP (with a
  league-specific correction), an opponent-needs model built live from the pick feed, a positional run detector, roster-need
  multipliers, and hard rules (K/D/ST only in the last two rounds, no QB2/TE2, endgame force-fill of required slots).
- Applies your research as boosts/fades (`data/overrides.json`) and a hand-written **conviction board** for rounds 1-3
  (`data/conviction.json`) that outranks everything else at any draft slot.
- Between your picks, asks Claude (Fable 5.1 by default, Opus fallback) for a plan: it may reorder within the engine's top 12
  and nudge projections; on the clock nothing waits for an LLM. Picks land in 2-5 seconds.
- Survives the real world: reconnects after "Duplicate Connection", disables ESPN's Autopick when it flips on, persists picks
  and re-syncs from the Pick History tab after a crash, parks the top 3 in ESPN's queue two picks out so a missed click still
  drafts your guy.

**What it needs**
- macOS with Chrome logged into ESPN (cookies are exported from Chrome's encrypted store via your Keychain), Python 3.12+,
  the `claude` CLI logged in (for the advisor), and Playwright Chromium.

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install playwright requests numpy pycryptodome && .venv/bin/playwright install chromium
cp config.example.json config.json      # fill in season, league_id, team_id, team_name, teams, rounds
.venv/bin/python tools_cookies.py       # exports espn_s2 + SWID (+ the Disney jar the room needs) to secrets*.json (0600)
.venv/bin/python pull.py                # snapshot league.json + players.json (projections, ADP, injuries, byes)
.venv/bin/python board.py --slot 4 --pick 4   # look at the engine's board
```
Write `data/overrides.json` (see `build_overrides.py` and `examples/`) and `data/conviction.json` (see
`examples/conviction.example.json`) from your own research. Put your league brief in `data/planner_brief.txt`
(`examples/planner_brief.example.txt`).

## Rehearse
ESPN's mock lobby offers a **league-specific practice draft** vs auto teams with your exact settings (30s clock):
```bash
.venv/bin/python live.py practice --slot 4          # full 14-round rehearsal; add --no-planner to skip Claude
.venv/bin/python evaluate.py data/picks_practice_<id>.json   # rank every team's projected starting lineup
```
Run several at different slots. `kick.py <practice_league_id>` opens the room from a second browser to test reconnects.

## Draft night
```bash
.venv/bin/python preflight.py            # cookies, API, settings, fresh pool, engine, planner: ALL GREEN or fix it
./run_draft.sh --headless                # caffeinate + live.py league; waits for the room to open, drafts all rounds
python3 watch.py                         # live console: every pick in the room + the bot's reasoning
```
Rules: ESPN allows ONE connection per team. Do not open the draft room anywhere else while the bot runs. If you must
take over, open the room yourself (this kicks the bot), then Ctrl-C it.

## Layout
`draftbot/engine.py` board · `draftbot/room.py` Playwright driver · `draftbot/planner.py` Claude advisor ·
`draftbot/espn.py` API reads · `live.py` loop · `preflight.py` · `evaluate.py` · `analyze.py` · `watch.py` · `tools_cookies.py`.
`LEARNINGS.md` has the ESPN plumbing and DOM facts that cost a day to learn; `STRATEGY.md` the drafting logic.

MIT. Author: Bryan Wilson, with Claude Fable 5.1. Not affiliated with ESPN or Disney.
