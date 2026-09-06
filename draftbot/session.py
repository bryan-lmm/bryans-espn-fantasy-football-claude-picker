"""requests.Session carrying your ESPN cookies (from secrets.json). Same interface as ctx.request.get: .get(url, headers=)."""
import json, requests
from .config import ROOT
class Resp:
    def __init__(self, r): self.r = r; self.status = r.status_code; self.ok = r.ok
    def json(self): return self.r.json()
    def text(self): return self.r.text
class Req:
    def __init__(self):
        s = json.loads((ROOT / "secrets.json").read_text())
        self.s = requests.Session()
        self.s.cookies.set("espn_s2", s["espn_s2"], domain=".espn.com"); self.s.cookies.set("SWID", s["SWID"], domain=".espn.com")
        self.s.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
    def get(self, url, headers=None): return Resp(self.s.get(url, headers=headers or {}, timeout=20))
class Ctx:
    """Duck-types the Playwright context the espn module expects."""
    def __init__(self): self.request = Req()
def cookies(): return json.loads((ROOT / "secrets.json").read_text())
