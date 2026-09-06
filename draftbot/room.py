"""Playwright driver for the ESPN draft room, using your full ESPN cookie jar (secrets_cookies.json).
RULE: ESPN allows ONE connection per team. While this runs, nobody opens the room elsewhere."""
import json, re, time
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from .config import ROOT, SEASON
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
PICK_RE = re.compile(r"^(?P<name>.+?) / (?P<team>[A-Z]{2,3}) (?P<pos>QB|RB|WR|TE|K|D/ST)\s*\|\s*R(?P<round>\d+), P(?P<pick>\d+) - (?P<owner>.+)$")

class Room:
    def __init__(self, headless=False, my_team=None):
        from .config import MY_TEAM_NAME
        self.my_team = my_team or MY_TEAM_NAME
        jar = json.loads((ROOT / "secrets_cookies.json").read_text())
        self.swid = next(c["value"] for c in jar if c["name"] == "SWID" and c["domain"].endswith("espn.com"))
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
        self.ctx = self.browser.new_context(viewport={"width": 1500, "height": 950}, user_agent=UA)
        for c in jar:
            ck = {k: c[k] for k in ("name", "value", "domain", "path", "secure", "httpOnly")}
            ck["sameSite"] = c["sameSite"] if c["sameSite"] in ("Lax", "Strict") else "None"
            if ck["sameSite"] == "None": ck["secure"] = True
            if c["expires"] and c["expires"] > 0: ck["expires"] = float(c["expires"])
            try: self.ctx.add_cookies([ck])
            except Exception: pass
        self.page = self.ctx.new_page()
        self.page.set_default_timeout(8000)
        self.picks = {}       # overall pick number -> dict(name, team, pos, round, owner)
        self.log = []
        self.persist_path = None
        self.url = None

    # ---- entry ----
    def open_league_room(self, league_id, team_id, timeout=60):
        self.url = f"https://fantasy.espn.com/football/draft?leagueId={league_id}&seasonId={SEASON}&teamId={team_id}&memberId={self.swid}"
        self.page.goto(self.url)
        return self.wait_ready(timeout=timeout)

    def save_picks(self):
        if self.persist_path:
            self.persist_path.write_text(json.dumps({str(k): v for k, v in self.picks.items()}))

    def load_picks(self, path):
        self.persist_path = path
        if path.exists():
            self.picks.update({int(k): v for k, v in json.loads(path.read_text()).items()})
        return len(self.picks)

    def settle(self):
        """After entering/re-entering the room: kill autopick if ESPN turned it on."""
        try:
            if self.disable_autopick(): self.log.append(("autopick_off_on_entry", time.time())); return True
        except Exception: pass
        return False

    def recover(self, reason=""):
        """Handle Duplicate Connection / disconnect modals or a vanished room: click Reconnect, else reload the room URL."""
        self.log.append(("recover", reason, time.time()))
        try:
            btn = self.page.get_by_role("button", name=re.compile(r"reconnect", re.I))
            if btn.count():
                btn.first.click(timeout=3000); time.sleep(2)
                if self.page.locator(".clock__digits").count(): self.settle(); return "reconnected"
        except Exception:
            pass
        try:
            self.page.goto(self.url or self.page.url); ok = self.wait_ready(timeout=60)
            if ok: self.settle()
            return "reloaded" if ok else "reload_failed"
        except Exception as e:
            return f"reload_error: {e!s:.80}"

    def start_practice(self, slot=4):
        """League-specific practice draft vs ESPN auto teams. Opens in a new page; we adopt it."""
        self.page.goto("https://fantasy.espn.com/football/mockdraftlobby"); time.sleep(3)
        self.page.get_by_role("button", name="Practice Draft").first.click(); time.sleep(1.5)
        self.page.locator("label.NumberedRadioGroup__ControlLabel").filter(has=self.page.locator(".NumberedRadioControl__Title", has_text=re.compile(rf"^{slot}$"))).click()
        with self.ctx.expect_page(timeout=20000) as np:
            self.page.locator("button.KonaForm__SubmitButton").click()
        self.page = np.value; self.page.set_default_timeout(8000)
        m = re.search(r"leagueId=(\d+)", self.page.url); self.league_id = int(m.group(1)) if m else None
        self.url = self.page.url
        return self.wait_ready()

    def wait_ready(self, timeout=60, reload_every=90):
        """Wait for the room to render its clock. Before the room opens ESPN shows 'Loading your draft'; reload periodically."""
        t0 = time.time(); last_reload = time.time(); last_msg = 0
        while time.time() - t0 < timeout:
            if self.page.locator(".clock__digits").count() > 0: return True
            if time.time() - last_reload > reload_every:
                try: self.page.reload()
                except Exception: pass
                last_reload = time.time()
            if time.time() - last_msg > 30:
                try:
                    print(time.strftime("%H:%M:%S"), "waiting for room:", self.page.inner_text("body")[:60].replace("\n", " / "), flush=True)
                    if int(time.time()) // 300 != int(last_msg) // 300: self.page.screenshot(path=str(ROOT / "data/waiting.png"))
                except Exception: pass
                last_msg = time.time()
            time.sleep(1)
        return False

    # ---- state ----
    def state(self):
        p = self.page
        js = """() => {
          const q = s => [...document.querySelectorAll(s)];
          const t = e => e ? e.innerText.replace(/\\n/g,' | ').trim() : null;
          return {
            clock: t(document.querySelector('.clock__digits')),
            otc: t(document.querySelector('.on-the-clock')),
            otcTeam: t(document.querySelector('.current-pick-module-container')),
            autopickBtn: t(document.querySelector('button.autopick-btn')),
            draftBtns: q('button').filter(b => /^draft$/i.test(b.textContent.trim())).length,
            rowBtns: [...new Set(q('.fixedDataTableRowLayout_rowWrapper button').map(b => b.textContent.trim()))],
            picks: q('li.pick-message__container').map(li => t(li)),
            roster: q('.roster-module tr, .roster tr').map(r => t(r)).filter(x => x),
            header: t(document.querySelector('.draft-header')),
            modal: (() => { const m = q('[role=dialog], .Modal, .modal').filter(e => !e.closest('#onetrust-consent-sdk') && e.offsetParent !== null); return m.length ? t(m[0]).slice(0,120) : null; })(),
            body0: document.body.innerText.slice(0, 80),
            discText: (document.body.innerText.match(/Duplicate Connection|disconnected|Reconnect|Exit Draft|Log in Required/i) || [null])[0],
          }; }"""
        s = p.evaluate(js)
        for line in s["picks"]:
            m = PICK_RE.match(line)
            if m:
                d = m.groupdict(); r, k = int(d["round"]), int(d["pick"])
                self.picks[(r - 1) * 12 + k] = {"name": d["name"].replace(" Q", "").strip(), "team": d["team"], "pos": d["pos"], "round": r, "owner": d["owner"]}
        self.save_picks()
        m = re.search(r"Pick (\d+)", s["otc"] or "")
        s["otc_pick"] = int(m.group(1)) if m else None
        s["disconnected"] = bool(s.get("discText")) or bool(s["modal"] and re.search(r"duplicate|disconnect|reconnect|connection", s["modal"], re.I))
        s["room_gone"] = s["clock"] is None or s["clock"].strip() in ("--:--", "-:--")
        s["otc_team"] = (s["otcTeam"] or "").split("|")[-1].strip() if s["otcTeam"] else None
        s["on_autopick"] = bool(s["autopickBtn"] and "disable" in s["autopickBtn"].lower())
        s["my_turn"] = s["draftBtns"] > 0 or (s["otc_team"] or "").lower() == self.my_team.lower()
        m = re.match(r"(\d+):(\d+)", s["clock"] or "")
        s["secs"] = int(m.group(1)) * 60 + int(m.group(2)) if m else None
        s["n_picks"] = len(self.picks)
        return s

    def detect_slot(self, team_name=None):
        """Our round-1 pick number, from the room: pre-draft header 'Your first pick: Round 1, Pick N', else the pick train
        ('PICK N | ... | <your team name>'), else None."""
        team_name = (team_name or self.my_team).lower()
        try:
            body = self.page.inner_text("body")
        except Exception:
            return None
        m = re.search(r"Your first pick:\s*Round 1,\s*Pick (\d+)", body, re.I)
        if m: return int(m.group(1))
        try:
            cells = self.page.evaluate("""() => [...document.querySelectorAll('.pick-component')].map(e => e.innerText.replace(/\\n/g,' | '))""")
        except Exception:
            cells = []
        mine = []
        for c in cells:
            mm = re.match(r"PICK (\d+)", c.strip(), re.I)
            if mm and team_name in c.lower(): mine.append(int(mm.group(1)))
        r1 = [n for n in mine if n <= 12]
        if r1: return min(r1)
        if mine:   # only later picks visible: invert the snake
            n = min(mine); rnd = (n - 1) // 12 + 1; pos = n - (rnd - 1) * 12
            return pos if rnd % 2 == 1 else 13 - pos
        return None

    def backfill_history(self):
        """Read the Pick History tab once (all picks so far), then return to Players."""
        p = self.page
        p.locator("button.tabs__link", has_text="Pick History").click(); time.sleep(0.8)
        rows = p.evaluate("""() => [...document.querySelectorAll('.fixedDataTableRowLayout_rowWrapper')].map(r => r.innerText.replace(/\\n/g,' | ')).filter(x => /^\\d+ \\|/.test(x))""")
        p.locator("button.tabs__link", has_text="Players").click()
        added = 0
        for row in rows:
            cells = [c.strip() for c in row.split("|") if c.strip()]
            # e.g. ['4', 'Jonathan Taylor', 'IND', 'RB', '<owner team name>', '362.3', '316.3', '5'] (an injury tag like 'Q' may follow the name)
            if len(cells) >= 5 and cells[0].isdigit():
                i = 2 if cells[2] in ("Q", "O", "D", "IR", "SSPD", "P") else 1
                name, team, pos, owner = cells[1], cells[i + 1], cells[i + 2], cells[i + 3]
                n = int(cells[0])
                if n not in self.picks and pos in ("QB", "RB", "WR", "TE", "K", "D/ST"):
                    self.picks[n] = {"name": name, "team": team, "pos": pos, "round": (n - 1) // 12 + 1, "owner": owner}; added += 1
        self.save_picks()
        return added

    # ---- actions ----
    def disable_autopick(self):
        b = self.page.locator("button.autopick-btn")
        if b.count() and "disable" in b.first.inner_text().lower():
            b.first.click(); self.log.append(("disable_autopick", time.time())); return True
        return False

    def search(self, text):
        """Type into the player search like a human and press Enter (React ignores programmatic fill)."""
        box = self.page.get_by_placeholder("Player Name")
        box.click(); self.page.keyboard.press("Meta+A"); self.page.keyboard.press("Backspace")
        if text:
            self.page.keyboard.type(text, delay=10); self.page.keyboard.press("Enter")
        else:
            self.page.keyboard.press("Enter")
        time.sleep(0.4)

    def set_position(self, pos):
        """Position dropdown: 'All Pos.', 'QB','RB','WR','TE','FLEX','D/ST','K'."""
        sel = self.page.locator("select").filter(has=self.page.locator("option", has_text=re.compile(r"^All Pos\.$"))).first
        sel.select_option(label=pos); time.sleep(0.4)

    def _row_for(self, name, pos=None):
        """Row for `name`: search+Enter (works), then position filter + gentle scroll as fallback."""
        needle = name.split(" D/ST")[0] if "D/ST" in name else name
        pat = re.compile(re.escape(needle.split()[-1] if " " in needle and "D/ST" not in name else needle), re.I)
        full = re.compile(re.escape(needle), re.I)
        self.search(needle)
        rows = self.page.locator(".fixedDataTableRowLayout_rowWrapper").filter(has_text=full)
        if rows.count(): return rows
        if pos:
            self.search(""); self.set_position("D/ST" if pos == "DST" else pos)
            body = self.page.locator(".fixedDataTableLayout_rowsContainer").first
            for attempt in range(8):
                rows = self.page.locator(".fixedDataTableRowLayout_rowWrapper").filter(has_text=full)
                if rows.count(): return rows
                body.hover(); self.page.mouse.wheel(0, 250); time.sleep(0.25)
        return self.page.locator(".fixedDataTableRowLayout_rowWrapper").filter(has_text=full)

    def draft(self, name, pos=None):
        """Click Draft on the row for `name`. Fails FAST (no waiting) if the player is already drafted or it's not our turn."""
        self.last_error = None
        rows = self._row_for(name, pos)
        if rows.count() == 0: self.last_error = "row not found"; return False
        row = rows.first
        if name.split(" D/ST")[0].split()[-1].lower() not in row.inner_text().lower(): self.last_error = "row mismatch"; return False
        btn = row.locator("button")
        if btn.count() == 0: self.last_error = "no button"; return False
        b = btn.first
        for _ in range(16):                      # up to ~4s for ESPN's ':03' lockout to become 'Draft'
            label = (b.text_content() or "").strip().lower(); cls = b.get_attribute("class") or ""
            if label == "drafted" or "Button--drafted" in cls: self.last_error = "already drafted"; return False
            if label == "queue": self.last_error = "not on clock (Queue button)"; return False
            if label == "draft" and "Button--disabled" not in cls: break
            time.sleep(0.25)
        else:
            self.last_error = f"button stuck at {label!r} {cls[:60]}"; return False
        try:
            b.click(timeout=3000)
        except Exception as e:
            self.last_error = f"click failed: {e!s:.80}"; return False
        self.log.append(("draft", name, time.time()))
        return True

    def queue(self, name, pos=None):
        rows = self._row_for(name, pos)
        if rows.count() == 0: return False
        b = rows.first.locator("button").filter(has_text=re.compile(r"^\s*queue\s*$", re.I))
        if b.count() == 0: return False
        b.first.click(); return True

    def clear_search(self):
        try: self.search(""); self.set_position("All Pos.")
        except Exception: pass

    def screenshot(self, path): self.page.screenshot(path=str(path))
    def close(self): self.browser.close(); self.pw.stop()
