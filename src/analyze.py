"""Synthetic syndicated lending portfolio: operational analytics and visual reporting."""
from pathlib import Path
import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
AS_OF = pd.Timestamp("2026-11-12")

def calculate(facilities: pd.DataFrame, events: pd.DataFrame):
    f_required = {"facility_id","borrower","industry","commitment_usd","utilisation_pct","risk_rating","spread_bps","maturity_date"}
    e_required = {"event_id","facility_id","event_type","due_date","settlement_date","expected_usd","actual_usd","docs_complete"}
    if not f_required.issubset(facilities.columns) or not e_required.issubset(events.columns):
        raise ValueError("Required input columns missing")
    if facilities.facility_id.duplicated().any() or events.event_id.duplicated().any():
        raise ValueError("Duplicate primary key")
    if not events.facility_id.isin(facilities.facility_id).all():
        raise ValueError("Unmatched servicing event facility_id")
    f, e = facilities.copy(), events.copy()
    if not f.utilisation_pct.between(0,100).all() or (f.commitment_usd<=0).any():
        raise ValueError("Invalid commitment or utilisation")
    f["maturity_date"] = pd.to_datetime(f.maturity_date, errors="raise")
    e["due_date"] = pd.to_datetime(e.due_date, errors="raise")
    e["settlement_date"] = pd.to_datetime(e.settlement_date, errors="coerce")
    e["expected_usd"] = pd.to_numeric(e.expected_usd, errors="raise")
    e["actual_usd"] = pd.to_numeric(e.actual_usd, errors="coerce")
    f["funded_exposure_usd"] = f.commitment_usd * f.utilisation_pct / 100
    e["cash_mismatch"] = e.settlement_date.notna() & (e.actual_usd-e.expected_usd).abs().gt(1)
    e["late_settlement"] = e.settlement_date.gt(e.due_date)
    e["overdue_open"] = e.settlement_date.isna() & e.due_date.lt(AS_OF)
    e["missing_documents"] = e.docs_complete.eq(0)
    e["any_exception"] = e[["cash_mismatch","late_settlement","overdue_open","missing_documents"]].any(axis=1)
    e["cash_variance_usd"] = e.actual_usd-e.expected_usd
    f["matures_next_12m"] = f.maturity_date.between(AS_OF, AS_OF+pd.DateOffset(years=1))
    grouped = e.groupby("facility_id").agg(events=("event_id","size"),exceptions=("any_exception","sum")).reset_index()
    fm = f.merge(grouped,on="facility_id",how="left").fillna({"events":0,"exceptions":0})
    queue = e[e.any_exception].merge(f[["facility_id","borrower","risk_rating"]],on="facility_id",how="left")
    queue = queue.sort_values(["overdue_open","cash_mismatch","missing_documents","late_settlement"],ascending=False)
    borrowers = f.groupby("borrower").funded_exposure_usd.sum().sort_values(ascending=False)
    summary = {
        "as_of": str(AS_OF.date()), "data_type": "synthetic",
        "facilities":int(len(f)), "servicing_events":int(len(e)),
        "total_commitment_usd":round(float(f.commitment_usd.sum()),2),
        "funded_exposure_usd":round(float(f.funded_exposure_usd.sum()),2),
        "utilisation_pct":round(float(f.funded_exposure_usd.sum()*100/f.commitment_usd.sum()),2),
        "events_with_any_exception":int(e.any_exception.sum()),
        "cash_mismatches":int(e.cash_mismatch.sum()),
        "late_settlements":int(e.late_settlement.sum()),
        "overdue_open_events":int(e.overdue_open.sum()),
        "missing_document_events":int(e.missing_documents.sum()),
        "maturing_facilities_next_12m":int(f.matures_next_12m.sum()),
        "top_5_borrower_exposure_share_pct":round(float(100*borrowers.head(5).sum()/f.funded_exposure_usd.sum()),2)
    }
    return fm,queue,summary

def render_dashboard(fm, summary, target):
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"axes.spines.top":False,"axes.spines.right":False})
    fig=plt.figure(figsize=(14,8),facecolor="#f6f8fb")
    gs=fig.add_gridspec(3,4,height_ratios=[.38,1,1],hspace=.65,wspace=.65)
    fig.text(.055,.96,"SYNDICATED LENDING  /  OPERATIONS RISK",fontsize=17,fontweight="bold",color="#13233a")
    fig.text(.055,.925,"Synthetic loan portfolio  |  12 Nov 2026  |  USD",fontsize=10,color="#56677a")
    tiles=[("FACILITIES",str(summary["facilities"])),("FUNDED EXPOSURE",f'${summary["funded_exposure_usd"]/1e6:.1f}m'),("UTILISATION",f'{summary["utilisation_pct"]:.1f}%'),("EVENTS WITH EXCEPTIONS",str(summary["events_with_any_exception"]))]
    for i,(label,value) in enumerate(tiles):
        ax=fig.add_subplot(gs[0,i]);ax.set_facecolor("white")
        for sp in ax.spines.values():sp.set_visible(False)
        ax.set_xticks([]);ax.set_yticks([])
        ax.text(.06,.7,label,transform=ax.transAxes,color="#64748b",fontsize=9,fontweight="bold")
        ax.text(.06,.12,value,transform=ax.transAxes,color="#13233a",fontsize=20,fontweight="bold")
    ax=fig.add_subplot(gs[1,:2]);ax.set_facecolor("white")
    industries=(fm.groupby("industry").funded_exposure_usd.sum()/1e6).sort_values()
    ax.barh(industries.index,industries.values,color="#1d648a")
    ax.set_title("Funded exposure by industry",loc="left",fontweight="bold",pad=12)
    ax.set_xlabel("USD millions");ax.grid(axis="x",alpha=.13)
    ax=fig.add_subplot(gs[1,2:]);ax.set_facecolor("white")
    labels=["Cash mismatches","Late settlements","Overdue open","Missing documents"]
    vals=[summary[k] for k in ["cash_mismatches","late_settlements","overdue_open_events","missing_document_events"]]
    ax.barh(labels[::-1],vals[::-1],color=["#d48741","#ca5c5c","#d6a14c","#6b88ad"][::-1])
    ax.set_title("Servicing exception flags",loc="left",fontweight="bold",pad=12)
    ax.set_xlabel("Count (categories may overlap)");ax.grid(axis="x",alpha=.13)
    ax=fig.add_subplot(gs[2,:2]);ax.set_facecolor("white")
    b=fm.groupby("borrower").funded_exposure_usd.sum().nlargest(6).sort_values()/1e6
    ax.barh(b.index.str.replace("Synthetic ","",regex=False),b.values,color="#3b8aab")
    ax.set_title("Largest borrower exposures",loc="left",fontweight="bold",pad=12)
    ax.set_xlabel("USD millions");ax.grid(axis="x",alpha=.13)
    ax=fig.add_subplot(gs[2,2:]);ax.set_facecolor("white")
    grades=fm.groupby("risk_rating").funded_exposure_usd.sum()/1e6
    ax.bar(grades.index.astype(str),grades.values,color="#6c78ad")
    ax.set_title("Funded exposure by synthetic risk grade",loc="left",fontweight="bold",pad=12)
    ax.set_xlabel("Risk grade (1 = strongest)");ax.set_ylabel("USD millions");ax.grid(axis="y",alpha=.13)
    fig.text(.055,.026,"Simulation only: no live bank transactions, borrower information or regulatory capital calculations.",fontsize=9,color="#64748b")
    fig.savefig(target,dpi=165,bbox_inches="tight",facecolor=fig.get_facecolor())
    plt.close(fig)

def main():
    facilities=pd.read_csv(ROOT/"data/facilities.csv")
    events=pd.read_csv(ROOT/"data/servicing_events.csv")
    fm,queue,summary=calculate(facilities,events)
    out=ROOT/"output"
    out.mkdir(exist_ok=True)
    fm.to_csv(out/"facility_risk.csv",index=False)
    queue.to_csv(out/"exception_queue.csv",index=False)
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    render_dashboard(fm,summary,out/"portfolio_dashboard.png")
    print(json.dumps(summary,indent=2))

if __name__=="__main__": main()
