"""Inspect the public Rakuten programme API schema."""
import json
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
BASE='https://backendapi.channel.rakuten.co.jp/platform/content/programs'
date=datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
url=BASE+'?platform=web&date='+date
req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://channel.rakuten.co.jp/'})
with urllib.request.urlopen(req,timeout=30) as response:
    data=json.load(response)
print('TOP', type(data).__name__, list(data)[:15] if isinstance(data,dict) else len(data))
print('SAMPLE',json.dumps(data,ensure_ascii=False)[:14000])
