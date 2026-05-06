# Andela ATC profile lookup

Scripts for resolving a list of names + emails to Andela ATC talent
profile URLs and certification statuses, runnable on any MacBook.

## What's in this folder

| File | Purpose |
| --- | --- |
| `andela_profile_lookup.py` | The main Python script. Takes a CSV in, writes a TSV out. |
| `run_andela_lookup.sh` | One-command wrapper. Sets up a venv + Playwright on first run. |
| `andela_lookup_console.js` | Zero-install alternative. Paste into Chrome DevTools on a logged-in tab. |
| `example_input.csv` | Five-row sample showing the expected input format. |

## Recommended path: the shell wrapper

```bash
chmod +x run_andela_lookup.sh
./run_andela_lookup.sh example_input.csv results.tsv
```

The first run downloads Playwright + Chromium (about 150 MB) into a
`.venv` folder next to the script, then opens a Chrome window. Sign in
to the Andela ATC with your `@andela.com` Google account once - the
session is saved under `~/.andela_lookup_chrome_profile` so future runs
skip the login step.

After the lookup finishes, open `results.tsv` in Numbers / Excel /
Google Sheets (it's tab-separated) or paste it directly into a
spreadsheet cell.

## Input format

CSV with at least two columns. The first row may be a header.

```
Name,Email
Lawrence Enehizena,lawstands@gmail.com
Olugbenga Solomon Falodun,falodunosolomon@gmail.com
```

Emails wrapped in Markdown link syntax (`[a@b.com](mailto:a@b.com)`)
are tolerated.

## Output format

Tab-separated, with header row:

```
#   Name                       Email                    Andela Profile URL                                    Status
1   Lawrence Enehizena         lawstands@gmail.com      https://app.andela.com/talent/ec3d1281-...           SKIP - certification in progress
2   Olugbenga Solomon Falodun  falodunosolomon@...      https://app.andela.com/talent/6348905f-...           Certified
```

Possible Status values:

- `Certified`
- `Not Certified`
- `SKIP - certification in progress`
- `SKIP - failed certification, can be reconsidered`
- `SKIP - deactivated`
- `SKIP - disbanded`
- `NOT FOUND` - no match in ATC search
- `ERROR` - lookup failed; second column has detail

When several profiles match, the script picks the first eligible
(non-SKIP) one. If every match is in a skip state, the first match is
returned with its skip flag.

## Manual setup (if you skip the wrapper)

```bash
brew install python@3.11        # if python3 --version is < 3.9
pip3 install playwright
python3 -m playwright install chromium
python3 andela_profile_lookup.py input.csv output.tsv
```

## Console-only fallback

When you only need a one-off lookup and don't want to install anything:

1. Sign in to https://app.andela.com/jobs in Chrome.
2. Click the magnifying-glass button at the bottom of the left sidebar
   so the search overlay is visible.
3. Open DevTools (`Cmd+Option+I`), go to the Console tab.
4. Open `andela_lookup_console.js`, edit the `EMAILS` array near the
   top, paste the whole file into the Console, and press Enter.
5. The TSV is printed at the end and copied to your clipboard.

The console version uses an in-page iframe to read each profile's
status, so the search overlay stays open between lookups.

## How it works

1. Open the search overlay (last button on the left sidebar).
2. Programmatically set the search input's value and dispatch an
   `input` event so React's debounced search fires.
3. After about two seconds, scrape `<a href="/talent/...">` links from
   the dropdown to get candidate profile URLs.
4. Visit each candidate profile and look at the page text for status
   markers (`Talent is in progress of being certified`,
   `failed certification`, `Not Certified`, `Certified`,
   `deactivated`, `disbanded`).
5. Pick the first eligible match; otherwise return the first match
   tagged with its skip reason.
6. Stream rows to the output file as soon as they're known so a crash
   or Ctrl-C never loses prior work.

## Troubleshooting

- **"Could not locate the search button on the sidebar"** - the ATC
  layout changed. Update `open_search_overlay()` in
  `andela_profile_lookup.py` with the new selector.
- **Login times out** - the browser window must be focused for SSO. If
  you closed it accidentally, just rerun the script.
- **Several profiles share an email** - the script logs all matches it
  considered to stdout but only writes one row per input email. Check
  the console output if you suspect a wrong pick.
- **Throttling** - if you're processing 200+ emails and start seeing
  empty results, increase `SEARCH_DEBOUNCE_MS` (in the JS) or the
  `time.sleep(2)` calls (in the Python script).
