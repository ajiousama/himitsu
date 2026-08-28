#!/usr/bin/env python3
import importlib.util
import pathlib
import sys

CORE_PATH = pathlib.Path(__file__).with_name("radiko_proxy_core.py")

if not CORE_PATH.exists():
    raise RuntimeError("radiko_proxy_core.py is missing. Download/extract the complete himitsu ZIP again.")

spec = importlib.util.spec_from_file_location("radiko_proxy_core_runtime", CORE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load radiko_proxy_core.py")
_core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = _core
spec.loader.exec_module(_core)

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

if __name__ == "__main__":
    _core.main()
