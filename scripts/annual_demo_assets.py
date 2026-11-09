"""Export only the explicitly public demo case; never export saved user uploads."""

import json

from src.annual_reports.continuity import workspace
from src.annual_reports.library import CASE_ID, DAYS, PRIOR_ID, bundle, prior_entry, sealed_entry


def demo_files():
    public = [prior_entry(), sealed_entry()]
    key = public[1]["issuer"]["company_id"]
    days = [public[0]["as_of"], *DAYS]
    return {
        **{f"issuer/{key}/{d}.json": workspace(key, d, public) for d in days},
        f"issuer/{key}/latest.json": workspace(key, days[-1], public),
        f"{PRIOR_ID}/latest.json": bundle(PRIOR_ID),
        f"{PRIOR_ID}/{days[0]}.json": bundle(PRIOR_ID),
        "index.json": public[::-1],
        f"{CASE_ID}/latest.json": bundle(CASE_ID),
        **{f"{CASE_ID}/{d}.json": bundle(CASE_ID, d) for d in DAYS},
    }


if __name__ == "__main__":
    print(json.dumps(demo_files(), ensure_ascii=False))
