"""Test helper: open the draft room from a SECOND browser for N seconds (ESPN kicks the first connection), then leave."""
import sys, time
from draftbot.room import Room
league = int(sys.argv[1]); secs = int(sys.argv[2]) if len(sys.argv) > 2 else 20
r = Room(headless=True)
print("kicker ready:", r.open_league_room(league, 1, timeout=40)); time.sleep(secs)
print("kicker sees:", (r.state().get("discText")), "| leaving"); r.close()
