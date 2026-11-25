import unittest
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from epg.coffee_epg_history import merge_history, JST, IDS

NOW = datetime(2026,11,26,7,0,tzinfo=JST)

def guide():
    r=ET.Element('tv')
    for cid in IDS:
        ET.SubElement(r,'channel',id=cid)
    return r

def programme(r,cid,days,title,minute=0):
    a=(NOW-timedelta(days=days)).replace(hour=10,minute=minute)
    b=a+timedelta(minutes=30)
    p=ET.SubElement(r,'programme',channel=cid,start=a.strftime('%Y%m%d%H%M%S %z'),stop=b.strftime('%Y%m%d%H%M%S %z'))
    ET.SubElement(p,'title').text=title

class HistoryTest(unittest.TestCase):
    def test_real_only_and_no_duplicates(self):
        r,old=guide(),guide()
        programme(r,IDS[0],1,'actual')
        programme(old,IDS[0],1,'old duplicate')
        programme(old,IDS[2],2,'Fuji actual')
        programme(old,IDS[3],8,'expired')
        programme(old,IDS[4],2,'番組表取得待ち')
        programme(r,IDS[5],0,'today')
        merge_history(r,old,NOW)
        merge_history(r,old,NOW)
        titles=[(p.get('channel'),p.findtext('title')) for p in r.findall('programme')]
        self.assertEqual(titles.count((IDS[0],'actual')),1)
        self.assertIn((IDS[1],'actual'),titles)
        self.assertIn((IDS[2],'Fuji actual'),titles)
        self.assertIn((IDS[5],'today'),titles)
        self.assertNotIn('expired',[t for _,t in titles])
        self.assertNotIn('番組表取得待ち',[t for _,t in titles])
        self.assertNotIn('old duplicate',[t for _,t in titles])
