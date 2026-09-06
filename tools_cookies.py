"""Pull your ESPN/Disney cookies out of Chrome (Chrome Safe Storage key from Keychain).
Writes secrets.json (espn_s2 + SWID for API) and secrets_cookies.json (full jar for the Playwright room). Both 0600."""
import os, shutil, sqlite3, subprocess, json, hashlib, time
from pathlib import Path
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
DOMS = ("espn.com", "go.com", "disney.com", "disneyplus.com", "bamgrid.com", "registerdisney.go.com", "dssott.com")
src = Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
tmp = Path("/tmp/ck.db"); shutil.copy(src, tmp)
pw = subprocess.check_output(["security", "find-generic-password", "-wa", "Chrome", "-s", "Chrome Safe Storage"]).strip()
key = PBKDF2(pw, b"saltysalt", 16, 1003)
def dec(blob, host):
    if not blob: return ""
    if blob[:3] != b"v10": return blob.decode(errors="replace")
    pt = AES.new(key, AES.MODE_CBC, b" " * 16).decrypt(blob[3:]); pt = pt[:-pt[-1]]
    if len(pt) > 32 and pt[:32] == hashlib.sha256(host.encode()).digest(): pt = pt[32:]
    return pt.decode(errors="replace")
con = sqlite3.connect(tmp); jar = []; core = {}
for host, name, val, enc, path, expires, secure, httponly, samesite in con.execute(
        "select host_key,name,value,encrypted_value,path,expires_utc,is_secure,is_httponly,samesite from cookies"):
    if not any(host.endswith(d) for d in DOMS): continue
    v = val or dec(enc, host)
    exp = (expires / 1_000_000 - 11644473600) if expires else -1
    jar.append({"name": name, "value": v, "domain": host, "path": path, "expires": exp if exp > 0 else -1,
                "secure": bool(secure), "httpOnly": bool(httponly), "sameSite": {0: "None", 1: "Lax", 2: "Strict"}.get(samesite, "Lax")})
    if name in ("espn_s2", "SWID") and host.endswith("espn.com"): core[name] = v
tmp.unlink()
assert core.get("espn_s2") and core.get("SWID"), core.keys()
for fn, data in (("secrets.json", core), ("secrets_cookies.json", jar)):
    p = Path(fn); p.write_text(json.dumps(data)); os.chmod(p, 0o600)
print(f"saved {len(jar)} cookies across {len({c['domain'] for c in jar})} domains; core ok")
