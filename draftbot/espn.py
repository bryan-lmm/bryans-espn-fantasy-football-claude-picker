"""Read side of ESPN's undocumented v3 fantasy API, through the logged-in Playwright context."""
import json, time
from .config import API, SEASON, POS

def _get(ctx, view, flt=None):
    headers = {"X-Fantasy-Filter": json.dumps(flt)} if flt else {}
    r = ctx.request.get(f"{API}?view={view}" if isinstance(view, str) else f"{API}?" + "&".join(f"view={v}" for v in view), headers=headers)
    if not r.ok:
        raise RuntimeError(f"ESPN {r.status}: {r.text()[:300]}")
    return r.json()

def league(ctx):
    return _get(ctx, ["mSettings", "mTeam", "mDraftDetail", "mRoster"])

def draft_state(ctx):
    """Picks so far. Each pick: {overall, round, teamId, playerId}. Plus inProgress/drafted flags."""
    j = _get(ctx, ["mDraftDetail"])
    d = j.get("draftDetail", {})
    picks = [{"overall": p["overallPickNumber"], "round": p["roundId"], "teamId": p["teamId"],
              "playerId": p["playerId"], "keeper": p.get("keeper", False)}
             for p in d.get("picks", []) if p.get("playerId", 0) > 0]
    return {"inProgress": d.get("inProgress"), "drafted": d.get("drafted"), "picks": picks, "raw_count": len(d.get("picks", []))}

def players(ctx, limit=1000):
    """Top players by ownership with ESPN season projections (league-scored) and ADP."""
    flt = {"players": {"limit": limit, "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
           "filterStatsForTopScoringPeriodIds": {"value": 2, "additionalValue": [f"00{SEASON}", f"10{SEASON}"]}}}
    j = _get(ctx, "kona_player_info", flt)
    out = []
    for p in j.get("players", []):
        pl = p["player"]
        proj = next((s for s in pl.get("stats", []) if s.get("statSourceId") == 1 and s.get("seasonId") == SEASON and s.get("scoringPeriodId") == 0), None)
        last = next((s for s in pl.get("stats", []) if s.get("statSourceId") == 0 and s.get("seasonId") == SEASON - 1 and s.get("scoringPeriodId") == 0), None)
        own = pl.get("ownership") or {}
        out.append({
            "id": pl["id"], "name": pl["fullName"], "pos": POS.get(pl.get("defaultPositionId"), str(pl.get("defaultPositionId"))),
            "proTeamId": pl.get("proTeamId"), "proj": round(proj["appliedTotal"], 1) if proj else None,
            "proj_week1": None, "last_season": round(last["appliedTotal"], 1) if last else None,
            "adp": round(own.get("averageDraftPosition", 999), 1), "pct_owned": round(own.get("percentOwned", 0), 1),
            "auction": own.get("auctionValueAverage"), "injury": pl.get("injuryStatus"), "injured": pl.get("injured"),
            "bye": None, "draft_rank_espn": (pl.get("draftRanksByRankType", {}).get("PPR") or {}).get("rank"),
            "eligible": pl.get("eligibleSlots", []),
        })
    return out

def pro_schedule(ctx):
    """Bye weeks by proTeamId."""
    r = ctx.request.get(f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}?view=proTeamSchedules_wl")
    j = r.json()
    byes = {}
    for t in j.get("settings", {}).get("proTeams", []):
        byes[t["id"]] = t.get("byeWeek")
    return byes
