-- SQLite-compatible analytical queries for synthetic syndicated-loan data
-- Import data/facilities.csv as facilities and data/servicing_events.csv as servicing_events.

-- Portfolio exposure and top borrower concentrations
SELECT borrower, industry, COUNT(*) AS facilities,
       ROUND(SUM(commitment_usd * utilisation_pct / 100.0),2) AS funded_exposure_usd
FROM facilities GROUP BY borrower,industry ORDER BY funded_exposure_usd DESC;

-- Servicing exception queue as of 2026-11-12 (cash tolerance = $1)
SELECT e.event_id, e.facility_id, f.borrower, f.risk_rating,
       e.event_type, e.due_date, e.settlement_date,
       ROUND(COALESCE(e.actual_usd,0) - e.expected_usd,2) AS indicative_variance_usd,
       CASE WHEN e.settlement_date IS NOT NULL
                      AND ABS(e.actual_usd-e.expected_usd)>1 THEN 1 ELSE 0 END AS cash_mismatch,
       CASE WHEN e.settlement_date>e.due_date THEN 1 ELSE 0 END AS late,
       CASE WHEN e.settlement_date IS NULL AND e.due_date<'2026-11-12' THEN 1 ELSE 0 END AS overdue_open,
       CASE WHEN e.docs_complete=0 THEN 1 ELSE 0 END AS missing_docs
FROM servicing_events e JOIN facilities f ON e.facility_id=f.facility_id
WHERE (e.settlement_date IS NOT NULL AND ABS(e.actual_usd-e.expected_usd)>1)
   OR e.settlement_date>e.due_date
   OR (e.settlement_date IS NULL AND e.due_date<'2026-11-12')
   OR e.docs_complete=0
ORDER BY overdue_open DESC, cash_mismatch DESC, missing_docs DESC;

-- Maturing in next 12 months
SELECT facility_id, borrower, maturity_date, risk_rating,
       ROUND(commitment_usd*utilisation_pct/100.0,2) AS funded_exposure_usd
FROM facilities
WHERE maturity_date BETWEEN '2026-11-12' AND '2027-11-12'
ORDER BY maturity_date;
