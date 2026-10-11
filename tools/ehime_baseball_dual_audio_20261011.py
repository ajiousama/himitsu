#!/usr/bin/env python3
"""Local-only temporary HLS mixer for Ehime high school baseball, 2026-10-11.
Video + right audio: eat; left audio: NHK Matsuyama R1.
Requires ffmpeg on PATH. Only use feeds in ways permitted by their providers.
Not an Internet redistribution server: HTTP binds to 127.0.0.1 only.
"""
import argparse
import http.server
import os
import pathlib
import shutil
import subprocess
import threading
import urllib.request
import xml.etree.ElementTree as ET

VIDEO = "https://eqlive-eqf412pron-live.eq-hls.wselive.stream.ne.jp/hls-live/1/mj0896ry3r397zq5/5eae7f34fb1683b14271f8d3_800_640x360.stream/chunklist_DVR.m3u8"
NHK_CONFIG = "https://www.nhk.or.jp/radio/config/config_web.xml"

def radio_url(service):
    request = urllib.request.Request(NHK_CONFIG, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=12) as response:
        root = ET.fromstring(response.read())
    for data in root.findall(".//stream_url/data"):
        if "松山" in (data.findtext("areajp") or "") or (data.findtext("area") or "").lower() == "matsuyama":
            url = (data.findtext(service) or "").strip()
            if url.startswith("https://"):
                return url
    raise RuntimeError("NHK松山 "+service+"の配信URLを公式設定から取得できませんでした")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fm", action="store_true", help="NHKがFMへ移った後はFM音声に変更して再起動")
    ap.add_argument("--nhk-delay-ms", type=int, default=0, help="NHK音声に加える遅延(ms)、正値のみ")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpegをインストールしてPATHへ追加してください")
    nhk = radio_url("fmhls" if args.fm else "r1hls")
    output = pathlib.Path("ehime_baseball_local_hls").resolve()
    output.mkdir(exist_ok=True)
    # Delay NHK if it leads the eat audio. If NHK is already behind, use a separate synchronization approach.
    delay = max(0, args.nhk_delay_ms)
    fc = (f"[1:a:0]aformat=channel_layouts=stereo,pan=mono|c0=0.5*c0+0.5*c1,adelay={delay}:all=1[left];"
          "[0:a:0]aformat=channel_layouts=stereo,pan=mono|c0=0.5*c0+0.5*c1[right];"
          "[left][right]join=inputs=2:channel_layout=stereo:map=0.0-FL|1.0-FR[a]")
    command = ["ffmpeg","-hide_banner","-loglevel","warning","-reconnect","1","-reconnect_streamed","1",
               "-reconnect_delay_max","3","-i",VIDEO,"-i",nhk,
               "-filter_complex",fc,"-map","0:v:0","-map","[a]","-c:v","copy",
               "-c:a","aac","-b:a","128k","-ac","2","-f","hls","-hls_time","4",
               "-hls_list_size","8","-hls_flags","delete_segments+omit_endlist",
               str(output/"index.m3u8")]
    proc = subprocess.Popen(command)
    os.chdir(output)
    class Handler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "http://localhost")
            super().end_headers()
    server = http.server.ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    print(f"ローカル再生: http://127.0.0.1:{args.port}/index.m3u8")
    print("終了はCtrl+C。FMへ切り替わったら --fm を指定して再起動")
    try:
        server.serve_forever()
    finally:
        proc.terminate()
        server.server_close()

if __name__ == "__main__":
    main()
