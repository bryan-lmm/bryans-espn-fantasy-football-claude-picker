import re, json, unicodedata
from .config import DATA
_SUF = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?", re.I)
def norm(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    n = _SUF.sub("", n.lower()); n = re.sub(r"[^a-z ]", "", n)
    return re.sub(r"\s+", " ", n).strip()
class Matcher:
    def __init__(self, pool):
        self.teams = {int(k): v for k, v in json.loads((DATA / "pro_teams.json").read_text()).items()}
        self.by_name = {}
        for p in pool:
            self.by_name.setdefault(norm(p["name"]), []).append(p)
    def find(self, name, team=None, pos=None):
        c = self.by_name.get(norm(name), [])
        if len(c) > 1 and team:
            c2 = [p for p in c if self.teams.get(p["proTeamId"], "") == team.upper()]
            c = c2 or c
        if len(c) > 1 and pos:
            c2 = [p for p in c if p["pos"] == pos.replace("/", "")]
            c = c2 or c
        return c[0] if c else None
