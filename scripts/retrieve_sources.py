"""Retrieve missing knowledge base sources within strict boundary rules.

Rules from K1:
- Only manifest rows with status 'not_retrieved'.
- Allowed hosts only: doi.org, dx.doi.org, www.doi.org, archimer.ifremer.fr,
  repository.oceanbestpractices.org, dspace.mit.edu, hdl.handle.net, argo.ucsd.edu,
  argodatamgt.org, www.argodatamgt.org, argopy.readthedocs.io, www.frontiersin.org,
  teos-10.org, teos-10.github.io, cpc.ncep.noaa.gov, climatedataguide.ucar.edu.
- One request at a time, 5 seconds apart.
- Maximum 40 requests total.
- Files under 60 MB.
- Save to knowledge/sources/ with source id in the filename.
- Record final URL, retrieved_on, and sha256 in knowledge/manifest.csv.
- If login wall, paywall, disallowed host, or no downloadable file, keep not_retrieved with reason.
"""

from __future__ import annotations

import csv
import hashlib
import logging
from pathlib import Path
import time
from urllib.parse import urlparse
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("retrieve_sources")

ALLOWED_HOSTS = {
    "doi.org",
    "dx.doi.org",
    "www.doi.org",
    "archimer.ifremer.fr",
    "repository.oceanbestpractices.org",
    "dspace.mit.edu",
    "hdl.handle.net",
    "argo.ucsd.edu",
    "argodatamgt.org",
    "www.argodatamgt.org",
    "argopy.readthedocs.io",
    "www.frontiersin.org",
    "teos-10.org",
    "teos-10.github.io",
    "cpc.ncep.noaa.gov",
    "climatedataguide.ucar.edu",
}

MAX_REQUESTS = 40
MAX_FILE_BYTES = 60 * 1024 * 1024  # 60 MB
REQUEST_DELAY_SECONDS = 5.0
OUTPUT_DIR = Path("knowledge/sources")
MANIFEST_PATH = Path("knowledge/manifest.csv")


def is_host_allowed(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in ALLOWED_HOSTS


def retrieve_sources() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        fieldnames = reader[0].keys() if reader else []

    requests_made = 0
    today_str = time.strftime("%Y-%m-%d")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "SIQVA-KnowledgeBase/1.0 (Educational/Scientific; Argo Ocean Research)"
    })

    updated_rows = []

    for row in reader:
        if row["status"] != "not_retrieved":
            updated_rows.append(row)
            continue

        if requests_made >= MAX_REQUESTS:
            logger.info("Reached maximum request limit (%d). Stopping K1 retrieval.", MAX_REQUESTS)
            updated_rows.append(row)
            continue

        source_id = row["id"]
        target_url = row["url_or_doi"]

        logger.info("Checking source [%s]: %s", source_id, target_url)

        if not is_host_allowed(target_url):
            logger.warning("Target host not in allowed hosts list: %s", target_url)
            row["notes"] = f"Skipped: Host '{urlparse(target_url).hostname}' is outside allowed hosts list."
            updated_rows.append(row)
            continue

        # Respect politeness delay
        if requests_made > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

        try:
            requests_made += 1
            # Step 1: Head or initial Get without following redirects blindly
            resp = session.get(target_url, allow_redirects=False, timeout=15)

            # Follow redirects manually up to 5 hops, ensuring each hop is allowed
            hops = 0
            curr_url = target_url
            curr_resp = resp
            redirect_disallowed = False

            while curr_resp.is_redirect and hops < 5:
                loc = curr_resp.headers.get("Location")
                if not loc:
                    break
                # Handle relative redirect
                if loc.startswith("/"):
                    parsed_curr = urlparse(curr_url)
                    loc = f"{parsed_curr.scheme}://{parsed_curr.netloc}{loc}"

                if not is_host_allowed(loc):
                    logger.warning("Redirect location disallowed: %s", loc)
                    redirect_disallowed = True
                    break

                curr_url = loc
                hops += 1
                if requests_made >= MAX_REQUESTS:
                    break
                time.sleep(REQUEST_DELAY_SECONDS)
                requests_made += 1
                curr_resp = session.get(curr_url, allow_redirects=False, timeout=15)

            if redirect_disallowed:
                row["notes"] = f"Skipped: Redirects outside allowed hosts to '{urlparse(curr_url).hostname}' (potential paywall/external repository)."
                updated_rows.append(row)
                continue

            if curr_resp.status_code != 200:
                # If landing on handle / obp, check if there was a direct link or 403
                logger.warning("HTTP status %d for %s", curr_resp.status_code, curr_url)
                row["notes"] = f"HTTP {curr_resp.status_code} at {curr_url}."
                updated_rows.append(row)
                continue

            # Check content length
            content_length = int(curr_resp.headers.get("Content-Length", 0))
            if content_length > MAX_FILE_BYTES:
                row["notes"] = f"Skipped: File size ({content_length} bytes) exceeds 60 MB limit."
                updated_rows.append(row)
                continue

            # Determine content type and extension
            content_type = curr_resp.headers.get("Content-Type", "").lower()
            if "pdf" in content_type or curr_url.lower().endswith(".pdf"):
                ext = ".pdf"
            elif "html" in content_type or curr_url.lower().endswith(".html") or curr_url.lower().endswith("/"):
                ext = ".html"
            elif "text" in content_type or curr_url.lower().endswith(".txt"):
                ext = ".txt"
            else:
                ext = ".bin"

            # Check special case: if repository landing page (like oceanbestpractices or doi), check for PDF download link inside allowed hosts
            if ext == ".html" and "oceanbestpractices.org/handle" in curr_url:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(curr_resp.text, "html.parser")
                pdf_link = None
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.lower().endswith(".pdf") or "/bitstream/" in href.lower():
                        if href.startswith("/"):
                            parsed = urlparse(curr_url)
                            pdf_link = f"{parsed.scheme}://{parsed.netloc}{href}"
                        elif href.startswith("http"):
                            pdf_link = href
                        break

                if pdf_link and is_host_allowed(pdf_link):
                    logger.info("Found PDF download on repository page: %s", pdf_link)
                    time.sleep(REQUEST_DELAY_SECONDS)
                    requests_made += 1
                    pdf_resp = session.get(pdf_link, stream=True, timeout=30)
                    if pdf_resp.status_code == 200:
                        curr_resp = pdf_resp
                        curr_url = pdf_link
                        ext = ".pdf"

            local_file = OUTPUT_DIR / f"{source_id}{ext}"
            content_bytes = bytearray()

            for chunk in curr_resp.iter_content(chunk_size=65536):
                if chunk:
                    content_bytes.extend(chunk)
                    if len(content_bytes) > MAX_FILE_BYTES:
                        raise ValueError(f"Exceeded 60 MB while streaming {curr_url}")

            local_file.write_bytes(content_bytes)
            sha = hashlib.sha256(content_bytes).hexdigest()
            logger.info("Saved [%s] (%d bytes, sha256=%s...): %s", source_id, len(content_bytes), sha[:12], local_file)

            # Update row
            row["status"] = "present"
            row["local_path"] = f"knowledge/sources/{local_file.name}"
            row["sha256"] = sha
            row["retrieved_on"] = today_str
            row["notes"] = f"Retrieved from {curr_url}."

            # Inspect license text if html or text
            if ext in (".html", ".txt"):
                text_sample = content_bytes.decode("utf-8", errors="ignore").lower()
                if "creative commons" in text_sample or "cc by" in text_sample:
                    row["license_as_seen"] = "Creative Commons"
                elif "noaa" in text_sample or "public domain" in text_sample or "cpc.ncep.noaa.gov" in curr_url:
                    row["license_as_seen"] = "US Public Domain / NOAA"

            updated_rows.append(row)

        except Exception as e:
            logger.error("Failed to retrieve %s: %s", source_id, e)
            row["notes"] = f"Retrieval failed: {e}"
            updated_rows.append(row)

    # Save updated manifest
    with open(MANIFEST_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_rows)

    logger.info("K1 retrieval complete. Made %d requests.", requests_made)


if __name__ == "__main__":
    retrieve_sources()

