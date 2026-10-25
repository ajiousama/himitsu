import unittest
from kick_gmcx_chapters import make_fixed_test_chapters
class Review(unittest.TestCase):
    def test_417_427_and_specials(self):
        v={"vod_id":"670c9223-f162-48b1-b684-e7f567d80b48","duration_seconds":58952}
        c=make_fixed_test_chapters(v,417,427,{})
        self.assertEqual(len(c),12)
        self.assertEqual([x["episode"] for x in c[:-1]],list(range(417,428)))
        self.assertEqual(c[-1]["special_key"],"417-427-specials-review")
        self.assertEqual((c[-1]["start_seconds"],c[-1]["duration_seconds"]),(38445,20507))
        self.assertEqual(c[-1]["review_status"],"special-time-unknown")
        for x,y in zip(c,c[1:]):self.assertEqual(x["stop_seconds"],y["start_seconds"])
if __name__=="__main__":unittest.main()
