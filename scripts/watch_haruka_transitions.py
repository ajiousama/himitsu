#!/usr/bin/env python3
"""Bounded live read-only watch for HLS discontinuities; fingerprint at detection time."""
import datetime as dt
import json
import time
from haruka_transition_fingerprints import CHANNELS, playlist, fingerprint
def main():
    seen=set()
    start=time.monotonic()
    polls=0
    while time.monotonic()-start < 360:
        for name,no in CHANNELS.items():
            try:
                segs=playlist(name,no)
                for i,(uri,duration,is_boundary) in enumerate(segs):
                    if not is_boundary or (name,uri) in seen: continue
                    seen.add((name,uri))
                    samples=[]
                    for j in range(max(i-2,0),min(i+3,len(segs))):
                        url,dur,mark=segs[j]
                        try: features=fingerprint(url)
                        except Exception as exc: features={"error":type(exc).__name__}
                        samples.append({"position":j-i,"duration":dur,"boundary":mark,**features})
                    print(json.dumps({"time_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                        "channel":name,"boundary_detected":True,"samples":samples}),flush=True)
            except Exception as exc:
                print(json.dumps({"channel":name,"error":str(exc)[:150]}),flush=True)
        polls+=1
        time.sleep(5)
    print(json.dumps({"done":True,"polls":polls,"boundaries":len(seen)}),flush=True)
if __name__=="__main__": main()
