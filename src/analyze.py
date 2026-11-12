"""Syndicated lending operations analytics. Uses synthetic portfolio CSVs."""
from pathlib import Path
from datetime import date, timedelta
import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
AS_OF = pd.Timestamp("2026-11-12")

def calculate(facilities: pd.DataFrame, events: pd.DataFrame):
    required_f = {"facility_id","borrower","industry","commitment_usd","utilisation_pct","risk_rating","spread_bps","maturity_date"}
    required_e = {"event_id","facility_id","event_type","due_date","settlement_date","expected_usd","actual_usd","docs_complete"}
    if not required_f.issubset(facilities.columns) or not required_e.issubset(events.columns):
        raise ValueError("Required dataset columns are missing")
    if facilities.facility_id.duplicated().any() or events.event_id.duplicated().any():
        raise ValueError("Duplicate facility or event identifiers")
    if not events.facility_id.isin(facilities.facility_id).all():
        raise ValueError("Orphaned servicing event with unknown facility")
    f = facilities.copy()
    e = events.copy()
    f["maturity_date"] = pd.to_datetime(f.maturity_date, errors="raise")
    e["due_date"] = pd.to_datetime(e.due_date, errors="raise")
    e["settlement_date"] = pd.to_datetime(e.settlement_date, errors="coerce")
    f["funded_exposure_usd"] = f.commitment_usd * f.utilisation_pct / 100
    e["cash_mismatch"] = e.settlement_date.notna() & (e.actual_usd - e.expected_usd).abs().gt(1)
    e["late_settlement"] = e.settlement_date.gt(e.due_date)
    e["overdue_open"] = e.settlement_date.isna() & e.due_date.lt(AS_OF)
    e["missing_documents"] = e.docs_complete.eq(0)
    e["any_exception"] = e[["cash_mismatch","late_settlement","overdue_open","missing_documents"]].any(axis=1)
    e["cash_variance_usd"] = (e.actual_usd - e.expected_usd).fillna(0)
    f["matures_next_12m"] = f.maturity_date.between(AS_OF, AS_OF + pd.DateOffset(years=1))
    counts = e.groupby("facility_id").agg(events=("event_id","size"), exceptions=("any_exception","sum")).reset_index()
    fm = f.merge(counts, on="facility_id", how="left").fillna({"events":0,"exceptions":0})
    exception_queue = e[e.any_exception].merge(f[["facility_id","borrower","risk_rating"]], on="facility_id")
    exception_queue = exception_queue.sort_values(["overdue_open","cash_mismatch","missing_documents","late_settlement"],ascending=False)
    exposure_by_borrower = f.groupby("borrower").funded_exposure_usd.sum().sort_values(ascending=False)
    summary = {
        "as_of":str(AS_OF.date()), "synthetic_data":True,
        "facilities":int(len(f)), "servicing_events":int(len(e)),
        "total_commitment_usd":round(float(f.commitment_usd.sum()),2),
        "funded_exposure_usd":round(float(f.funded_exposure_usd.sum()),2),
        "utilisation_pct":round(float(100*f.funded_exposure_usd.sum()/f.commitment_usd.sum()),2),
        "events_with_any_exception":int(e.any_exception.sum()),
        "cash_mismatches":int(e.cash_mismatch.sum()),
        "late_settlements":int(e.late_settlement.sum()),
        "overdue_open_events":int(e.overdue_open.sum()),
        "missing_document_events":int(e.missing_documents.sum()),
        "maturing_facilities_next_12m":int(f.matures_next_12m.sum()),
        "top_5_borrower_exposure_share_pct":round(float(100*exposure_by_borrower.head(5).sum()/f.funded_exposure_usd.sum()),2),
    }
    return fm, exception_queue, summary

def main():
    facilities=pd.read_csv(ROOT/"data/facilities.csv")
    events=pd.read_csv(ROOT/"data/servicing_events.csv")
    fm,exc,s=calculate(facilities,events)
    out=ROOT/"output";out.mkdir(exist_ok=True)
    fm.to_csv(out/"facility_risk.csv",index=False)
    exc.to_csv(out/"exception_queue.csv",index=False)
    (out/"summary.json").write_text(json.dumps(s,indent=2),encoding="utf-8")
    exposure=fm.groupby("industry").funded_exposure_usd.sum().sort_values(ascending=True)/1e6
    flags=pd.Series({k:s[k] for k in ["cash_mismatches","late_settlements","overdue_open_events","missing_document_events"]})
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    exposure.plot.barh(ax=axes[0],color="#2563eb")
    axes[0].set(xlabel="Funded exposure ($m)",title="Industry exposure")
    axes[1].barh(flags.index,flags.values,color="#e07a29")
    axes[1].set(xlabel="Events",title="Control exception flags")
    fig.suptitle("Syndicated Lending: Synthetic Portfolio & Servicing Controls",fontsize=13)
    fig.tight_layout();fig.savefig(out/"portfolio_dashboard.png",dpi=160)
    print(json.dumps(s,indent=2))

if __name__=="__main__": main()
