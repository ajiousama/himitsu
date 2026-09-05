#!/usr/bin/env python3
from __future__ import annotations

import radiko_cloud_start as base
import ehime_catv_hls as ehime_hls

core = base.core
core.BUILD = "20260905-radio-tv-ehime-hls-v1"

_previous_get = core.Handler.do_GET
_previous_head = core.Handler.do_HEAD


def _ehime_do_get(self):
    if ehime_hls.handle_request(self):
        return
    return _previous_get(self)


def _ehime_do_head(self):
    if ehime_hls.handle_head(self):
        return
    return _previous_head(self)


core.Handler.do_GET = _ehime_do_get
core.Handler.do_HEAD = _ehime_do_head


if __name__ == "__main__":
    core.main()
