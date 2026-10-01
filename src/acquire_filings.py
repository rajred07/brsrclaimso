"""Materialize only the ten registered filing pairs from NSE's public listing."""
import csv
import hashlib
import json
import re
from datetime import datetime, timezone

import pymupdf
import requests

from .dataset import filings
from .llm import ROOT, load_config
from .xbrl_parser import parse_xbrl, store_facts

SYMBOLS = {"infosys": "INFY", "reliance": "RELIANCE", "tata-steel": "TATASTEEL",
           "mahindra": "M&M", "larsen-toubro": "LT", "hul": "HINDUNILVR",
           "jsw-steel": "JSWSTEEL", "tcs": "TCS", "wipro": "WIPRO", "itc": "ITC"}
ENDPOINT = "https://www.nseindia.com/api/corporate-bussiness-sustainabilitiy"


def name_key(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold().replace(" ltd", " limited"))


def acquire(config, exclude=()):
    rows = filings(config)
    provenance_path = ROOT / "data/provenance.json"
    provenance = json.loads(provenance_path.read_text()) if provenance_path.exists() else []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*",
                            "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-bussiness-sustainabilitiy-reports"})
    session.get("https://www.nseindia.com/", timeout=25).raise_for_status()
    for filing in rows:
        if filing["filing_id"] in exclude:
            continue
        if filing["pdf_path_or_url"] and filing["xbrl_path_or_url"] and all(
                (ROOT / filing[k]).is_file() for k in ("pdf_path_or_url", "xbrl_path_or_url")):
            facts = parse_xbrl(ROOT / filing["xbrl_path_or_url"], filing["company"], filing["reporting_year"], filing["filing_id"])
            store_facts(facts, ROOT / config["data"]["facts_db"])
            print(f"Existing verified pair: {filing['filing_id']} ({len(facts)} numeric facts)", flush=True)
            continue
        symbol = SYMBOLS[filing["filing_id"].removesuffix("-" + filing["reporting_year"])]
        start_year = int(filing["reporting_year"][:4])
        params = {"symbol": symbol, "from_date": f"01-04-{start_year+1}", "to_date": f"31-03-{start_year+2}"}
        response = session.get(ENDPOINT, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        candidates = [r for r in data.get("data", []) if r.get("fyFrom") == start_year and r.get("fyTo") == start_year+1
                      and r.get("attachmentFile") and r.get("xbrlFile")]
        if not candidates:
            raise ValueError(f"No complete public pair for {symbol}")
        # Preserve the listing and use its latest dated row for this exact FY.
        row = max(candidates, key=lambda r: datetime.strptime(r["submissionDate"], "%d-%b-%Y"))
        directory = ROOT / "data/filings" / filing["filing_id"]
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "nse_listing.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        paths = {"pdf": directory / "report.pdf", "xbrl": directory / "filing.xml"}
        for kind, key in (("xbrl", "xbrlFile"), ("pdf", "attachmentFile")):
            downloaded = session.get(row[key], timeout=45)
            if kind == "xbrl" and downloaded.status_code == 404:
                for suffix in ("_WEB__1_.xml", "_WEB__.xml"):
                    alternate = row[key].replace("_WEB.xml", suffix)
                    downloaded = session.get(alternate, timeout=45)
                    if downloaded.ok:
                        row[key] = alternate
                        break
            downloaded.raise_for_status()
            if kind == "pdf" and b"%PDF" not in downloaded.content[:1024]:
                raise ValueError(f"Download is not a PDF: {row[key]}")
            paths[kind].write_bytes(downloaded.content)
        facts = parse_xbrl(paths["xbrl"], year=filing["reporting_year"], filing_id=filing["filing_id"])
        company = facts[0]["company"]
        if name_key(company) != name_key(row["companyName"]):
            raise ValueError(f"NSE/XML company mismatch: {company} vs {row['companyName']}")
        with pymupdf.open(paths["pdf"]) as document:
            pages = len(document)
            if not any(p.get_text().strip() for p in document):
                raise ValueError("PDF has no readable text")
        filing.update(company=company, pdf_path_or_url=paths["pdf"].relative_to(ROOT).as_posix(),
                      xbrl_path_or_url=paths["xbrl"].relative_to(ROOT).as_posix())
        store_facts(facts, ROOT / config["data"]["facts_db"])
        provenance = [p for p in provenance if p["filing_id"] != filing["filing_id"]]
        provenance.append({"filing_id": filing["filing_id"], "company": company, "reporting_year": filing["reporting_year"],
                           "source_urls": {"pdf": row["attachmentFile"], "xbrl": row["xbrlFile"]},
                           "listing_url": response.url, "download_date": datetime.now(timezone.utc).isoformat(),
                           "sha256": {kind: hashlib.sha256(path.read_bytes()).hexdigest() for kind, path in paths.items()},
                           "pdf_pages": pages, "numeric_facts": len(facts)})
        with (ROOT / config["data"]["filings"]).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        print(f"Downloaded verified pair: {filing['filing_id']} ({pages} PDF pages; {len(facts)} numeric facts)", flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--exclude", nargs="*", default=[])
    acquire(load_config(), parser.parse_args().exclude)
