import sys
import unittest
from pathlib import Path
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from analyze import calculate

class LoanAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.f=pd.DataFrame([dict(facility_id="F1",borrower="Borrower A",industry="Technology",commitment_usd=1000,utilisation_pct=60,risk_rating=2,spread_bps=150,maturity_date="2027-02-01")])
        self.e=pd.DataFrame([
          dict(event_id="E1",facility_id="F1",event_type="Repayment",due_date="2026-11-01",settlement_date="2026-11-03",expected_usd=100,actual_usd=98,docs_complete=0),
          dict(event_id="E2",facility_id="F1",event_type="Interest",due_date="2026-11-02",settlement_date=None,expected_usd=50,actual_usd=None,docs_complete=1)])
    def test_exceptions_and_exposure(self):
        f,e,s=calculate(self.f,self.e)
        self.assertEqual(s["funded_exposure_usd"],600)
        self.assertEqual(s["cash_mismatches"],1)
        self.assertEqual(s["late_settlements"],1)
        self.assertEqual(s["overdue_open_events"],1)
        self.assertEqual(s["missing_document_events"],1)
        self.assertEqual(s["events_with_any_exception"],2)
        self.assertEqual(s["maturing_facilities_next_12m"],1)
    def test_orphan_rejected(self):
        e=self.e.copy();e.loc[0,"facility_id"]="UNKNOWN"
        with self.assertRaises(ValueError):calculate(self.f,e)

if __name__=="__main__":unittest.main()
