#!/usr/bin/env python3
from __future__ import annotations

import os

# Render exposes its HTTP port through PORT. Configure the existing Radiko
# gateway before importing it so module-level HOST/PORT use cloud values.
os.environ.setdefault("RADIKO_PROXY_HOST", "0.0.0.0")
os.environ.setdefault("RADIKO_PROXY_PORT", os.environ.get("PORT", "10000"))

import radiko_proxy_core

if __name__ == "__main__":
    radiko_proxy_core.main()
