#!/usr/bin/env python3
"""
andela_profile_lookup.py
========================

Look up Andela ATC talent profiles by email, capture profile URLs, and
flag certification status.

INPUT
-----
A CSV file with two columns: Name, Email (header optional).

    Name,Email
    Lawrence Enehizena,lawstands@gmail.com
    Olugbenga Solomon Falodun,falodunosolomon@gmail.com
    ...

OUTPUT
------
A tab-separated file with: #, Name, Email, Profile URL, Status.
Open it in Excel / Numbers / Google Sheets, or paste into any spreadsheet.

Status values:
    Certified
    Not Certified
    SKIP - certification in progress
    SKIP - failed certification, can be reconsidered
    SKIP - deactivated / disbanded
    NOT FOUND
    ERROR (with detail)

ONE-TIME SETUP (about 2 minutes)
--------------------------------
You need Python 3.9+ and the Playwright library.

    # 1. Install Python (skip if `python3 --version` shows 3.9+)
    brew install python@3.11

    # 2. Install Playwright + the bundled Chromium browser
    pip3 install playwright
    python3 -m playwright install chromium

USAGE
-----
    python3 andela_profile_lookup.py input.csv output.tsv

The first time you run it, a Chrome window opens. Sign in to the
Andela ATC (https://app.andela.com) with your @andela.com Google account.
Your session is saved to ~/.andela_lookup_chrome_profile so subsequent
runs skip the login step.

NOTES
-----
- The script reuses one tab for everything; close it only when finished.
- If you have many emails (50+), expect roughly 6-8 seconds per lookup.
- Results are flushed to disk as they complete, so a crash never loses
  prior work. Re-running with the same input/output just overwrites.
- Profiles flagged with the SKIP statuses are still included in the
  output - they are tagged so you can filter, not removed.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    sys.stderr.write(
        "playwright is not installed. Run:\n"
        "  pip3 install playwright\n"
        "  python3 -m playwright install chromium\n"
    )
    sys.exit(1)


ATC_URL = "https://app.andela.com/jobs"
PROFILE_PREFIX = "https://app.andela.com/talent/"
USER_DATA_DIR = Path.home() / ".andela_lookup_chrome_profile"

# JS snippet that programmatically sets the search input value
# and dispatches the React-compatible input event.
SET_SEARCH_VALUE_JS = """
(value) => {
    const input = document.querySelector('input[placeholder*="Search"]');
    if (!input) return false;
    input.focus();
    const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
    ).set;
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
}
"""

EXTRACT_LINKS_JS = """
() => Array.from(document.querySelectorAll('a[href^="/talent/"]'))
        .map(a => ({ href: a.href, text: a.textContent.trim().slice(0, 120) }))
"""

STATUS_REGEX_JS = """
() => {
    const t = document.body.innerText;
    const flags = (t.match(
        /Talent is in progress of being certified|failed certification|can be reconsidered|disbanded|deactivated|Not Certified|Certified/gi
    ) || []);
    return [...new Set(flags)];
}
"""


def detect_status(flags: list[str]) -> str:
    """Translate raw flags to a human-readable status string."""
    fl = {f.lower() for f in flags}
    if "talent is in progress of being certified" in fl:
        return "SKIP - certification in progress"
    if "failed certification" in fl and "can be reconsidered" in fl:
        return "SKIP - failed certification, can be reconsidered"
    if "deactivated" in fl:
        return "SKIP - deactivated"
    if "disbanded" in fl:
        return "SKIP - disbanded"
    if "not certified" in fl:
        return "Not Certified"
    if "certified" in fl:
        return "Certified"
    return "Status unknown"


def open_search_overlay(page) -> None:
    """Click the magnifying-glass button in the left sidebar."""
    # The sidebar has roughly 5-6 icon buttons; the search one is at the
    # bottom of the icon stack. Anchor on the SearchIcon SVG.
    candidates = [
        'button:has(svg[data-testid="SearchIcon"])',
        '[aria-label="Search"]',
        'a:has(svg[data-testid="SearchIcon"])',
    ]
    for sel in candidates:
        try:
            page.locator(sel).first.click(timeout=2000)
            page.wait_for_selector('input[placeholder*="Search"]', timeout=3000)
            return
        except Exception:
            continue
    raise RuntimeError(
        "Could not locate the search button on the sidebar. The ATC UI "
        "may have changed - update open_search_overlay() in this script."
    )


def search_email(page, email: str) -> list[dict]:
    """Type the email into the open search overlay and return matching links."""
    page.evaluate(SET_SEARCH_VALUE_JS, email)
    time.sleep(2)  # Wait for debounced server-side search
    return page.evaluate(EXTRACT_LINKS_JS) or []


def verify_status(page, url: str) -> str:
    """Navigate to a profile and return its detect_status() label."""
    page.goto(url)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except PWTimeout:
        pass
    time.sleep(1)  # let the cert banner render
    flags = page.evaluate(STATUS_REGEX_JS)
    return detect_status(flags)


def read_input(path: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with open(path, newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        has_header = "email" in sample.lower() and "name" in sample.lower()
        reader = csv.reader(f)
        if has_header:
            next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            name = row[0].strip()
            email = row[1].strip().lstrip("[").rstrip("]")
            # Strip Markdown link syntax like "[email](mailto:email)"
            if email.startswith("mailto:"):
                email = email[len("mailto:"):]
            if "](mailto:" in email:
                email = email.split("](mailto:")[0]
            if email and "@" in email:
                rows.append((name, email))
    return rows


def write_row(writer, fp, row) -> None:
    writer.writerow(row)
    fp.flush()


def lookup(input_path: str, output_path: str) -> None:
    rows = read_input(input_path)
    print(f"Loaded {len(rows)} entries from {input_path}")
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p, \
         open(output_path, "w", newline="") as out_fp:
        writer = csv.writer(out_fp, delimiter="\t")
        writer.writerow(["#", "Name", "Email", "Andela Profile URL", "Status"])
        out_fp.flush()

        ctx = p.chromium.launch_persistent_context(
            str(USER_DATA_DIR),
            headless=False,
            channel="chrome",
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ATC_URL)

        print(
            "If a login page appears, sign in with your @andela.com Google "
            "account. The script will continue once the Jobs Dashboard loads."
        )
        try:
            page.wait_for_url("**/jobs", timeout=300_000)  # 5 min
        except PWTimeout:
            print("Login timed out after 5 minutes. Exiting.")
            ctx.close()
            return
        page.wait_for_load_state("networkidle", timeout=10_000)

        for i, (name, email) in enumerate(rows, start=1):
            print(f"[{i}/{len(rows)}] {name} <{email}> ...", end=" ", flush=True)

            # 1. Open the search overlay (closes after every navigation).
            try:
                page.goto(ATC_URL, wait_until="domcontentloaded")
                open_search_overlay(page)
            except Exception as e:
                print(f"ERROR opening search: {e}")
                write_row(writer, out_fp, (i, name, email, "ERROR", str(e)[:200]))
                continue

            # 2. Search by email.
            try:
                links = search_email(page, email)
            except Exception as e:
                print(f"ERROR during search: {e}")
                write_row(writer, out_fp, (i, name, email, "ERROR", str(e)[:200]))
                continue

            if not links:
                print("not found")
                write_row(
                    writer, out_fp,
                    (i, name, email, "NOT FOUND", "No matches in ATC search"),
                )
                continue

            # 3. Walk candidates; pick the first eligible profile, or the first
            #    flagged one if every candidate is in a skip state.
            picked_url: str | None = None
            picked_status: str | None = None
            for link in links:
                try:
                    status = verify_status(page, link["href"])
                except Exception as e:
                    status = f"ERROR verifying status: {e}"

                if picked_url is None:
                    picked_url, picked_status = link["href"], status
                if not status.startswith("SKIP") and status != "Status unknown":
                    picked_url, picked_status = link["href"], status
                    break

            print(picked_status)
            write_row(writer, out_fp, (i, name, email, picked_url, picked_status))

        print(f"\nDone. Wrote {len(rows)} rows to {output_path}")
        ctx.close()


def main() -> None:
    if len(sys.argv) != 3:
        sys.stderr.write(
            "Usage: python3 andela_profile_lookup.py <input.csv> <output.tsv>\n"
        )
        sys.exit(1)
    lookup(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
