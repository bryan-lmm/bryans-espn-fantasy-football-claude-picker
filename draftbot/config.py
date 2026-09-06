"""All league-specific settings live in config.json next to this repo's root. Nothing personal is hardcoded."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
_cfg_path = ROOT / "config.json"
_cfg = json.loads(_cfg_path.read_text()) if _cfg_path.exists() else {}
SEASON = int(_cfg.get("season", 2026))
LEAGUE_ID = int(_cfg.get("league_id", 0))
MY_TEAM_ID = int(_cfg.get("team_id", 1))
MY_TEAM_NAME = _cfg.get("team_name", "My Team")
TEAMS = int(_cfg.get("teams", 12))
ROUNDS = int(_cfg.get("rounds", 14))
PLANNER_MODEL = _cfg.get("planner_model", "claude-fable-5-1")
DATA = ROOT / "data"
API = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"
POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}
SLOT = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DST", 17: "K", 20: "BE", 21: "IR", 23: "FLEX"}
