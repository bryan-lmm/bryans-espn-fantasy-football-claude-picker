# Learnings: ESPN plumbing, draft-room DOM, and what broke in rehearsal (Sept 2026)

## ESPN API (read side)
- `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{leagueId}?view=...`
  with cookies `espn_s2` + `SWID`. Views: mSettings, mTeam, mDraftDetail, mRoster, kona_player_info (with an
  `X-Fantasy-Filter` JSON header; a `limit` requires a sort, e.g. `sortPercOwned`).
- Past seasons: `.../leagueHistory/{leagueId}?seasonId=YYYY&view=mDraftDetail&view=mTeam&view=mSettings`.
- Projections: kona_player_info stats entry with statSourceId=1, seasonId=season, scoringPeriodId=0 -> `appliedTotal` is
  already scored to your league. `ownership.averageDraftPosition` is ESPN ADP.
- mDraftDetail does NOT update live during a draft. It does give the full pick skeleton (teamId per pick) beforehand, and
  `draftSettings.pickOrder`. ESPN randomizes an unset order one hour before the draft: detect your slot from the room.
- Cookies: `espn_s2` is HttpOnly (page JS can't read it). Export from Chrome's cookie DB with the Chrome Safe Storage
  Keychain key (tools_cookies.py). Two cookies suffice for the API; the DRAFT ROOM needs the fuller Disney/ESPN jar.
  Cookies are not device-bound: the same file works from another machine. Disney's login page bounces automated
  browsers, so never try to log in from Playwright.

## Draft room (Playwright)
- URL: `fantasy.espn.com/football/draft?leagueId=..&seasonId=..&teamId=..&memberId={SWID}` (memberId required).
- ONE connection per team: a second one gets "Duplicate Connection" (button "Reconnect"). ESPN flips Autopick ON whenever
  you get kicked or your clock expires; it stays on until you click "Disable Autopick" (`button.autopick-btn`).
- Selectors (Sept 2026 build): clock `.clock__digits` ("--:--" while disconnected); `.on-the-clock` text
  "ON THE CLOCK: PICK N" (can lag a pick); `.current-pick-module-container` includes the team name (reliable);
  pick feed `li.pick-message__container` innerText "Name / TEAM POS | R1, P4 - Owner" (only ~26 most recent: parse
  incrementally); players table rows `.fixedDataTableRowLayout_rowWrapper` (virtualized, ~18 rows; mouse.wheel jumps ~30
  rows); row button reads Queue (not your turn), ":03" (3s lockout when you come on the clock), Draft, or Drafted
  (disabled); no confirm dialog; search box placeholder "Player Name" ignores programmatic fill, needs keystrokes + Enter;
  position dropdown is the `select` whose options include "All Pos."; tabs `button.tabs__link`; Pick History rows are
  FixedDataTable rows "N | Name | TEAM | POS | Owner | ...". A hidden OneTrust dialog exists: exclude `#onetrust-consent-sdk`.
- Pre-draft the room shows "Loading your draft" until ESPN opens it (~50 min early), then a countdown clock and a header
  "Your first pick: Round 1, Pick N".
- League-specific PRACTICE drafts (mock lobby -> "Practice Draft") use your exact settings vs auto teams, 30s clock,
  auto teams pick every ~3s; the temp league dies after the draft. Several can run in parallel.
- Playwright: set default timeout on the ADOPTED popup page too; `page.goto()` returns a truthy Response.

## Bugs found in rehearsal
- Blind clicks on disabled buttons burn 6-8s each: inspect the button label/class first, fail fast.
- Gating "my turn" on the pick number cost picks (it lags); gate on the team name.
- Starter-level VOR baselines made bench-level RB/WR negative so K/D/ST won mid-draft: deeper baselines + hard exclusions.
- Deep baselines from BOOSTED projections drift when you fade players: compute baselines from raw projections.
- The advisor's boosts written into the research overrides file accumulated across rehearsals: use a per-draft runtime file.
- TE1 drifts to replacement level unless its need multiplier escalates by round.
