#!/usr/bin/env python3
"""Guarded HTTP client. ALL scripted traffic to the target goes through here.
Reads work/target.json + work/scope_hosts.txt. Enforces host allowlist, research header,
cross-process rate limit, daily hard stop, allowlisted redirects, redacted JSONL logging.
  Library: from guard import request;  CLI: python3 work/guard.py GET URL [-H 'K: V'] [-d BODY] [-s session] [-o file]
"""
import argparse, datetime as dt, fcntl, json, os, re, sys, time
from pathlib import Path
from urllib.parse import urlsplit, urljoin
import httpx

WORK = Path(__file__).resolve().parent
CFG = json.loads((WORK / "target.json").read_text())
COUNT_FILE, LOCK_FILE = WORK / "request_count.txt", WORK / ".guard.lock"
SCOPE_FILE, TRAFFIC_DIR, SESSIONS_DIR = WORK / "scope_hosts.txt", WORK / "traffic", WORK / "sessions"
HDR = tuple(CFG["research_header"])
DAILY_STOP, MIN_INTERVAL, MAX_REDIRECTS = CFG["daily_stop"], CFG["min_interval"], 5
REDACT = {"cookie", "set-cookie", "authorization", "x-auth-token"}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 H1-sudouid0"
_TOK = re.compile(r'("(?:[a-z_]*token[a-z_]*|appsid|password|otp|code|secret)"\s*:\s*")([^"]+)(")', re.I)


class Refused(Exception):
    pass


def _allow():
    if not SCOPE_FILE.exists():
        return set()
    return {l.split("#", 1)[0].strip().lower() for l in SCOPE_FILE.read_text().splitlines() if l.split("#", 1)[0].strip()}


def _check(url):
    u = urlsplit(url)
    if u.scheme not in ("http", "https"):
        raise Refused(f"bad scheme {url!r}")
    if (u.hostname or "").lower() not in _allow():
        raise Refused(f"host not in allowlist: {u.hostname!r}")


def _today():
    return dt.date.today().isoformat()


def _state(fh):
    st = {"date": _today(), "count": 0, "last": 0.0}
    d = fh.read().split()
    if d:
        try:
            last = float(d[2]) if len(d) > 2 else 0.0
            st = {"date": d[0], "count": int(d[1]), "last": last} if d[0] == _today() else {**st, "last": last}
        except (ValueError, IndexError):
            raise Refused(f"cannot parse {COUNT_FILE}")
    return st


def _slot():
    COUNT_FILE.touch(exist_ok=True)
    with open(LOCK_FILE, "a+") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            with open(COUNT_FILE, "r+") as fh:
                st = _state(fh)
                if st["count"] >= DAILY_STOP:
                    raise Refused(f"daily stop {st['count']}/{DAILY_STOP}")
                w = st["last"] + MIN_INTERVAL - time.time()
                if w > 0:
                    time.sleep(w)
                st["count"] += 1
                st["last"] = time.time()
                fh.seek(0); fh.truncate()
                fh.write(f"{st['date']} {st['count']} {st['last']:.3f}\n")
                return st["count"]
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def _body(b, lim=200_000):
    try:
        t = _TOK.sub(r"\1<redacted>\3", b.decode())
    except UnicodeDecodeError:
        return f"<binary {len(b)} bytes>"
    return t if len(t) <= lim else t[:lim] + "...<truncated>"


def _log(e):
    TRAFFIC_DIR.mkdir(exist_ok=True)
    with open(TRAFFIC_DIR / f"{_today()}.jsonl", "a") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")


_clients, _jars = {}, {}


def _client(session):
    if session not in _clients:
        jar = None
        if session:
            from http.cookiejar import MozillaCookieJar
            jar = MozillaCookieJar(str(SESSIONS_DIR / f"{session}.cookies.txt"))
            jar.load(ignore_discard=True, ignore_expires=True)
            _jars[session] = jar
        _clients[session] = httpx.Client(timeout=30.0, follow_redirects=False, cookies=jar)
    return _clients[session]


def request(method, url, *, headers=None, data=None, json_body=None, follow_redirects=True, note="", session=None):
    method = method.upper()
    h = {"User-Agent": UA, **(headers or {})}
    h[HDR[0]] = HDR[1]
    c = _client(session)
    for _ in range(MAX_REDIRECTS + 1):
        _check(url)
        n, t0 = _slot(), time.time()
        req = c.build_request(method, url, headers=h, content=data, json=json_body)
        r = c.send(req); r.read()
        if session and session in _jars:
            _jars[session].save(ignore_discard=True, ignore_expires=True)
            os.chmod(_jars[session].filename, 0o600)
        red = lambda d: {k: "<redacted>" if k.lower() in REDACT else v for k, v in d.items()}
        _log({"n": n, "ts": dt.datetime.now().isoformat(timespec="seconds"), "note": note, "method": method, "url": url,
              "req_headers": red(dict(req.headers)), "req_body": _body(req.content) if req.content else None,
              "status": r.status_code, "elapsed": round(time.time() - t0, 3),
              "resp_headers": red(dict(r.headers)), "resp_body": _body(r.content)})
        if follow_redirects and r.is_redirect and "location" in r.headers:
            url = urljoin(url, r.headers["location"])
            if r.status_code in (301, 302, 303) and method != "HEAD":
                method, data, json_body = "GET", None, None
            continue
        return r
    raise Refused("too many redirects")


def count():
    if not COUNT_FILE.exists():
        return 0
    with open(COUNT_FILE) as f:
        return _state(f)["count"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("method", nargs="?"); ap.add_argument("url", nargs="?")
    ap.add_argument("-H", action="append", default=[]); ap.add_argument("-d"); ap.add_argument("-o")
    ap.add_argument("-s", "--session"); ap.add_argument("-i", action="store_true"); ap.add_argument("--count", action="store_true")
    a = ap.parse_args()
    if a.count:
        sys.exit(print(f"{_today()}: {count()}/{DAILY_STOP}"))
    if not (a.method and a.url):
        ap.error("method and url required")
    hd = {k.strip(): v.strip() for k, _, v in (x.partition(":") for x in a.H)}
    try:
        r = request(a.method, a.url, headers=hd, data=a.d.encode() if a.d else None, session=a.session)
    except Refused as e:
        sys.exit(f"REFUSED: {e}")
    print(f"{r.status_code} {r.url} ({len(r.content)}B) [count {count()}]", file=sys.stderr)
    if a.i:
        for k, v in r.headers.items():
            print(f"{k}: {'<redacted>' if k.lower() in REDACT else v}", file=sys.stderr)
    Path(a.o).write_bytes(r.content) if a.o else sys.stdout.write(r.text)
