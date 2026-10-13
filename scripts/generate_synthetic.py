"""Generate the SYNTHETIC dataset. Nothing here is real household, rainfall or pest data.
Deliberately messy: missing rainfall days, a conflicting pest report, a report with unclear location."""
import csv, json
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "synthetic"
AS_OF = date(2026, 10, 12)
days = [AS_OF - timedelta(days=i) for i in range(20, -1, -1)]  # 21 days ending AS_OF

rain = {
    "Z-LOK-A": [0,12.4,3.1,0,0,22.0,8.5,0,0,1.2,0,35.6,18.2,0,0,6.3,0,0,14.0,2.2,0],
    "Z-LOK-B": [0,0,0,0,2.4,0,0,0,None,None,None,None,None,None,5.1,0,0,0,0,None,None],
}
with open(OUT / "rainfall.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["zone_id", "date", "rain_mm"])
    for z, vals in rain.items():
        for d, v in zip(days, vals):
            w.writerow([z, d.isoformat(), "" if v is None else v])

hh = [
 ("HH-001","C-FELELE","Z-LOK-A","maize","2026-09-02",1.2,"SMS"),
 ("HH-002","C-FELELE","Z-LOK-A","maize","2026-08-25",0.8,"USSD"),
 ("HH-003","C-FELELE","Z-LOK-A","maize","2026-09-25",1.5,"SMS"),
 ("HH-004","C-ADANKOLO","Z-LOK-A","rice","2026-08-20",1.0,"visit"),
 ("HH-005","C-ADANKOLO","Z-LOK-A","rice","2026-08-01",2.0,"SMS"),
 ("HH-006","C-ADANKOLO","Z-LOK-A","rice","2026-09-10",0.6,"USSD"),
 ("HH-007","C-KOTON","Z-LOK-B","maize","2026-09-05",1.1,"SMS"),
 ("HH-008","C-KOTON","Z-LOK-B","rice","2026-08-15",0.9,"visit"),
 ("HH-009","C-KOTON","Z-LOK-B","maize","2026-09-28",1.3,"USSD"),
]
cl = {"C-FELELE":"Felele maize collective (synthetic)","C-ADANKOLO":"Adankolo rice group (synthetic)","C-KOTON":"Koton-Karfe mixed farmers (synthetic)"}
json.dump([dict(household_id=a,cluster_id=b,cluster_name=cl[b],zone_id=c,crop=d,planting_date=e,plot_ha=g,preferred_channel=h,synthetic=True)
           for a,b,c,d,e,g,h in hh], open(OUT/"households.json","w"), indent=2)

pests = [
 dict(report_id="PR-001",cluster_id="C-FELELE",date="2026-10-08",pest="fall armyworm",crops=["maize"],severity="moderate",source="officer_visit",verified=True),
 dict(report_id="PR-002",cluster_id="C-FELELE",date="2026-10-10",pest="fall armyworm",crops=["maize"],severity="high",source="farmer_whatsapp",verified=False),
 dict(report_id="PR-003",cluster_id="C-ADANKOLO",date="2026-10-05",pest="stem borer",crops=["rice"],severity="low",source="whatsapp_group_forward",verified=False),
 dict(report_id="PR-004",cluster_id="C-KOTON",date="2026-09-27",pest="fall armyworm",crops=["maize"],severity="low",source="officer_visit",verified=True),
 dict(report_id="PR-005",cluster_id=None,date="2026-10-11",pest="unknown caterpillar",crops=["maize"],severity="unknown",source="whatsapp_group_forward",verified=False,note="location unclear"),
]
json.dump(pests, open(OUT/"pest_reports.json","w"), indent=2)
print("synthetic data written to", OUT)
