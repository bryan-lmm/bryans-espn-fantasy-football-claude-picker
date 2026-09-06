# Drafting logic (generalizable version of what won the rehearsals)

1. **Measure your league's scarcity, don't assume it.** Print projected points at ranks 1/3/6/12/15/18/24/36 per position
   in your scoring (`board.py` data). Cliffs and plateaus tell you where value disappears. In a 2026 full-PPR, 4-pt-pass-TD
   league: RB fell off a cliff from #15 to #24, WR was flat from #9 to #24, QB was flat from #3 to #15 with one outlier,
   elite TE was +53 over TE6.
2. **Measure your room, don't assume it.** Ten years of `leagueHistory` gives position mix by round and how early QBs/TEs go
   versus ESPN ADP. Encode it as `league_adp()` multipliers so survival odds reflect these people, not the internet.
3. **Round 1-3 by conviction, not by formula.** Write an ordered list per round from durability research; the bot follows it
   at any slot, with a 2-per-position guard. Never spend a top pick on a player with a season-ending risk profile.
4. **Fill starters with urgency that grows by round; never draft QB2/TE2** (the waiver wire has QB17-24 every week).
5. **Late rounds are upside only:** rising roles, handcuffs to your own RBs. K and D/ST in the last two rounds.
6. **Research goes into boosts/fades on individual players; baselines stay on raw projections.**
7. **The LLM advises off the clock, within the engine's top 12, and is discarded if late.** On the clock: arithmetic + click.
8. **Score rehearsals** with `evaluate.py` (optimal projected starting lineup vs every other team) on both raw and
   research-adjusted projections; the gap between the two is the price of your fades. Keep it near 1%.
