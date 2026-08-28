#!/usr/bin/env python3
import importlib.util
import os
import pathlib
import sys
import urllib.parse
import urllib.request

LAUNCHER_BUILD = "20260828-1338"
CORE_PATH = pathlib.Path(__file__).with_name("radiko_proxy_core.py")
CORE_URL = "https://raw.githubusercontent.com/ajiousama/himitsu/main/radiko_proxy_core.py"

print(f"[radiko] launcher build: {LAUNCHER_BUILD}", flush=True)


def refresh_core():
    try:
        req = urllib.request.Request(CORE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if not data.startswith(b"#!/usr/bin/env python3"):
            raise RuntimeError("downloaded core did not look like Python source")
        tmp = CORE_PATH.with_suffix(".py.tmp")
        tmp.write_bytes(data)
        tmp.replace(CORE_PATH)
        print("[radiko] core auto-update: OK", flush=True)
    except Exception as e:
        if CORE_PATH.exists():
            print(f"[radiko] core auto-update skipped: {type(e).__name__}: {e}", flush=True)
        else:
            raise RuntimeError(f"radiko_proxy_core.py download failed: {type(e).__name__}: {e}") from e


refresh_core()

if not CORE_PATH.exists():
    raise RuntimeError("radiko_proxy_core.py is missing")

spec = importlib.util.spec_from_file_location("radiko_proxy_core_runtime", CORE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load radiko_proxy_core.py")
_core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = _core
spec.loader.exec_module(_core)

_original_do_GET = _core.Handler.do_GET

def _diagnostic_do_GET(self):
    path = urllib.parse.urlsplit(self.path).path
    if path != "/ready":
        return _original_do_GET(self)

    def fail(stage, exc):
        msg = f"FAIL stage={stage} error={type(exc).__name__}: {exc}\n"
        print("[radiko] " + msg.strip(), flush=True)
        self.sendb(502, msg.encode("utf-8", "replace"), "text/plain; charset=utf-8")

    try:
        local = _core.local_area(force=True)
    except Exception as e:
        return fail("local_area", e)

    mail = os.environ.get("RADIKO_MAIL", "").strip()
    pw = os.environ.get("RADIKO_PASSWORD", "").strip()
    mode = "free"
    if mail and pw:
        try:
            _core.premium_login(force=True)
            mode = "premium"
        except Exception as e:
            return fail("premium_login", e)

    try:
        _core.auth_area(local, force=True)
    except Exception as e:
        return fail("auth_area", e)

    try:
        ss = _core.stations()
    except Exception as e:
        return fail("station_list", e)

    body = f"OK {local} mode={mode} stations={len(ss)} auth=pc-html5-api build={getattr(_core, 'BUILD', 'unknown')} launcher={LAUNCHER_BUILD}\n"
    self.sendb(200, body.encode(), "text/plain; charset=utf-8")

_core.Handler.do_GET = _diagnostic_do_GET

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

if __name__ == "__main__":
    _core.main()
