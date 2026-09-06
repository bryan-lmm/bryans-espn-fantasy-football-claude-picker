"""Live console: every pick in the room as it lands (ours marked), plus the bot's own events. Ctrl-C to stop."""
import os, time, sys, json
import json as _j; _c = _j.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")))
PICKS = f"data/picks_league_{_c['league_id']}.json"; LOG = "data/draft_night.out"; ME = _c.get("team_name", "").lower()
os.chdir(os.path.dirname(os.path.abspath(__file__)))
seen = set(); pos_log = os.path.getsize(LOG) if os.path.exists(LOG) else 0
print("watching... (picks + bot events)", flush=True)
while True:
    try:
        if os.path.exists(PICKS):
            p = json.load(open(PICKS))
            for k, v in sorted(p.items(), key=lambda x: int(x[0])):
                if k in seen: continue
                seen.add(k); n = int(k); rnd = (n - 1) // 12 + 1
                me = "  <== US" if v["owner"].lower() == ME else ""
                print(f"{time.strftime('%H:%M:%S')}  R{rnd:>2} #{n:>3}  {v['owner'][:22]:<22} {v['name']} ({v['pos']}){me}", flush=True)
        if os.path.exists(LOG):
            with open(LOG) as f:
                f.seek(pos_log); chunk = f.read(); pos_log = f.tell()
            for line in chunk.splitlines():
                if '"ev": "state"' in line or not line.startswith("{"): continue
                try: d = json.loads(line)
                except Exception: continue
                ev = d.get("ev")
                if ev == "planner": print(f"{d['t']}  ADVISOR ({d.get('ms',0)//1000}s): {d.get('note')}", flush=True)
                elif ev == "on_clock": print(f"{d['t']}  ON CLOCK pick {d['pick']} | top: " + ", ".join(f"{c[0]} ({c[1]})" for c in d['candidates'][:4]), flush=True)
                elif ev == "picked": print(f"{d['t']}  >>> PICKED {d.get('name')} ({d.get('pos')}) in {d.get('ms')}ms", flush=True)
                elif ev == "queued": print(f"{d['t']}  queued for {d['for_pick']}: {', '.join(d['names'])}", flush=True)
                elif ev in ("disconnected", "recover", "error", "autopick_disabled", "autopick_disabled_on_turn", "draft_click_failed", "resync_history"): print(f"{d['t']}  [{ev}] {json.dumps({k: v for k, v in d.items() if k not in ('ev', 't')})[:160]}", flush=True)
        time.sleep(2)
    except KeyboardInterrupt:
        break
    except Exception as e:
        print("watch error:", e, flush=True); time.sleep(2)
