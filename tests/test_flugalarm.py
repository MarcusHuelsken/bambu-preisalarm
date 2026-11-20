import json
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import flugalarm as f

CFG = json.loads((Path(__file__).resolve().parents[1]/"flugalarm_config.json").read_text())


def leg(a, b, duration=15, price=2700, token=None):
    points = [a, "DOH", b]
    flights = [{"departure_airport":{"id":x,"time":"2027-08-10 10:00"},
                "arrival_airport":{"id":y,"time":"2027-08-11 06:00"},
                "airline":"Qatar Airways","flight_number":"QR123"}
               for x,y in zip(points, points[1:])]
    obj = {"flights":flights, "total_duration":duration*60,"price":price}
    if token:
        obj["departure_token"] = token
    return obj


def example():
    return {
        "origin":"FRA","departure_date":"2027-08-10","return_date":"2027-08-26",
        "price_eur":2600,"hours_out":15,"hours_back":16,"stops_out":1,
        "stops_back":1,"baggage":"unknown","carriers":"Qatar Airways",
        "seats_guaranteed":False
    }


class TestFlightAlert(unittest.TestCase):
    def test_query_has_four_people_and_all_airports(self):
        params=f.query(CFG,list(CFG["airports"]),date(2027,8,10),date(2027,8,26))
        self.assertEqual(params["departure_id"],"DUS,FRA,CGN,AMS")
        self.assertEqual(params["adults"],2)
        self.assertEqual(params["children"],2)
        self.assertEqual(params["stops"],"2")

    def test_dates_and_rotation(self):
        dates,total=f.dates_to_check(CFG,datetime(2026,11,20,tzinfo=timezone.utc))
        self.assertEqual((len(dates),total),(4,27))
        self.assertEqual(len(set(dates)),4)
        collected=set()
        for offset in range(27):
            batch,_=f.dates_to_check(CFG,datetime(2026,11,20,tzinfo=timezone.utc)+timedelta(days=offset))
            collected.update(batch)
        self.assertEqual(len(collected),27)

    def test_weighted_price_and_hard_filters(self):
        cheap=example()
        dear=example()
        dear["price_eur"]=3500
        self.assertGreater(f.score(cheap,CFG)["score"],f.score(dear,CFG)["score"])
        dear["stops_back"]=2
        self.assertIsNone(f.score(dear,CFG))
        dear["stops_back"]=1
        dear["return_date"]="2027-08-30"
        self.assertIsNone(f.score(dear,CFG))

    def test_parse_pair_verified_return(self):
        result=f.parse_pair(leg("FRA","BKK",15,2400),
                            leg("BKK","FRA",16,2650),
                            date(2027,8,10),date(2027,8,26),CFG)
        self.assertEqual(result["price_eur"],2650)
        self.assertEqual(result["calendar_days"],17)
        self.assertEqual(result["baggage"],"unknown")
        self.assertIsNone(f.parse_pair(leg("FRA","BKK"),leg("BKK","AMS"),date(2027,8,10),date(2027,8,26),CFG))

    def test_two_request_round_trip_search(self):
        with patch.object(f,"api_request",side_effect=[
            {"best_flights":[leg("AMS","BKK",15,2500,token="chosen")]},
            {"best_flights":[leg("BKK","AMS",16,2650)]}
        ]) as request:
            offers,calls=f.find_offers(CFG,date(2027,8,10),date(2027,8,26))
        self.assertEqual((len(offers),calls),(1,2))
        self.assertEqual(offers[0]["origin"],"AMS")
        self.assertEqual(request.call_args_list[1].args[0]["departure_token"],"chosen")

    def test_alert_no_duplicate(self):
        item=example()
        item.update(f.score(item,CFG))
        alerts=f.find_alerts([item],CFG,{})
        self.assertEqual(len(alerts),1)
        self.assertEqual(f.find_alerts([item],CFG,{alerts[0]["alert_key"]:2600}),[])

    def test_no_key_no_network(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaisesRegex(RuntimeError,"SERPAPI_API_KEY"):
                f.api_request({"engine":"google_flights"})


if __name__ == "__main__":
    unittest.main()
