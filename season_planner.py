"""Judgment pass on the weekly optimizer output: Fable reads our lineup, bench audit, free agents, and this week's research,
then returns concrete moves with reasons. usage: season_planner.py [--week N] [--model claude-fable-5-1]"""
import json, subprocess, sys, argparse, time
from draftbot.config import DATA
from draftbot.planner import claude_bin
ap = argparse.ArgumentParser(); ap.add_argument("--week", type=int, default=1); ap.add_argument("--model", default="claude-fable-5-1"); a = ap.parse_args()
weekly = json.loads((DATA / f"weekly_wk{a.week}.json").read_text())
research = {}
for f in ("research_waivers_wk1.json", "research_dst_wk1.json", "news_roster_wk1.json"):
    p = DATA / f
    if p.exists(): research[f] = json.loads(p.read_text())
prompt = f"""You are the general manager for an ESPN fantasy football team (league settings, waiver rules and playoff format are in
config.json / the research below). GOAL: maximize the chance of winning THIS week's head-to-head while keeping the roster's
rest-of-season value. D/ST scoring rewards low opponent points/yards (opponent implied total is the best predictor), sacks, turnovers.
A deterministic optimizer produced this week's starters (matchup-adjusted: ESPN weekly projection x Vegas game environment + research
boosts), a bench audit vs the free-agent pool, and top free agents. Research files (industry consensus, news, D/ST method) are attached.
Answer as JSON only:
{{"lineup_changes": [{{"slot": "...", "out": "...", "in": "...", "why": "..."}}],
 "adds": [{{"add": "...", "drop": "...", "why": "...", "urgency": "now|before_thursday|before_sunday|watch"}}],
 "dst_call": {{"start": "...", "why": "..."}},
 "disagreements_with_optimizer": ["..."],
 "watch_list": ["player: what would trigger a move"],
 "summary": "3 sentences max"}}

OPTIMIZER OUTPUT:
{json.dumps(weekly)}

RESEARCH:
{json.dumps(research)[:60000]}
"""
t0 = time.time()
out = subprocess.run([claude_bin(), "-p", "--model", a.model, "--output-format", "json", prompt], capture_output=True, text=True, timeout=400)
res = json.loads(out.stdout); text = res.get("result", ""); text = text[text.find("{"): text.rfind("}") + 1]
plan = json.loads(text); plan["_ms"] = int((time.time() - t0) * 1000); plan["_cost"] = res.get("total_cost_usd"); plan["_model"] = a.model
(DATA / f"season_plan_wk{a.week}.json").write_text(json.dumps(plan, indent=1))
print(f"[{a.model} {plan['_ms']//1000}s ${plan['_cost']:.2f}]")
print("SUMMARY:", plan.get("summary"))
print("DST:", plan.get("dst_call"))
for x in plan.get("lineup_changes", []): print("LINEUP:", x)
for x in plan.get("adds", []): print("ADD/DROP:", x)
for x in plan.get("disagreements_with_optimizer", []): print("DISAGREE:", x)
for x in plan.get("watch_list", []): print("WATCH:", x)
