#!/usr/bin/env python3
"""
Scrap carbide price tracker — daily scraper.

Rides a manually-established Sandvik Coromant session (no credentials stored here)
to pull a recycling price quote and append it to data/prices.json.

First-time / re-login setup (run on a machine with a display, or over VNC):

    python3 scrape.py --login

That opens a real browser. Log in by hand, get to the recycling page, then press
Enter in the terminal. The session is saved into ./browser-profile and reused by
every later headless run.

Daily run (cron):

    python3 scrape.py

If the session has expired (Sandvik forces a logout, password change, etc.) the
run exits non-zero with a clear message so cron can alert you. Re-run --login.
"""

import os
import sys
import json
import pathlib
import datetime
from playwright.sync_api import sync_playwright

# --- config -----------------------------------------------------------------

ROOT = pathlib.Path(__file__).resolve().parent
USER_DATA_DIR = ROOT / "browser-profile"          # persistent session lives here
DATA_FILE = ROOT / "data" / "prices.json"

RECYCLING_PAGE = "https://www.sandvik.coromant.com/en-gb/services/recycling"
QUOTE_URL = "https://www.sandvik.coromant.com/recyclingvendor/createpricequoteforcountry"

# Reference quantity to quote. Price scales linearly, so this only sets the
# precision of the per-kg figure; 50 kg matches what was captured.
QUOTE_UNIT = "kg"
QUOTE_VALUE = "50"

KG_PER_LB = 0.45359237

# In an unprivileged LXC the Chromium sandbox can't initialise and /dev/shm is
# tiny, so set CARBIDE_NO_SANDBOX=1 there. Leave it unset on a normal desktop.
LAUNCH_ARGS = (["--no-sandbox", "--disable-dev-shm-usage"]
               if os.environ.get("CARBIDE_NO_SANDBOX") else [])


# --- helpers ----------------------------------------------------------------

def fail(msg: str) -> "NoReturn":
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_history() -> list:
    if DATA_FILE.exists():
        text = DATA_FILE.read_text().strip()
        if text:
            return json.loads(text)
    return []


def save_row(row: dict) -> None:
    history = load_history()
    # Replace today's entry if the job re-runs, otherwise append.
    if history and history[-1].get("date") == row["date"]:
        history[-1] = row
    else:
        history.append(row)
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(history, indent=2) + "\n")


# --- main -------------------------------------------------------------------

def run(login_mode: bool) -> None:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=not login_mode,
            viewport={"width": 1280, "height": 900},
            args=LAUNCH_ARGS,
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(RECYCLING_PAGE, wait_until="domcontentloaded", timeout=60_000)

            if login_mode:
                print("\n  A browser window is open.")
                print("  1. Log in to Sandvik Coromant.")
                print("  2. Navigate to the recycling page and confirm you can see a price.")
                print("  3. Come back here and press Enter to save the session.\n")
                input("  Press Enter when done... ")
                print("Session saved to", USER_DATA_DIR)
                return

            # Headless daily path. If we got bounced to the identity server,
            # the session is gone.
            if "login.sandvik" in page.url:
                fail("Session expired (redirected to login). Re-run: python3 scrape.py --login")

            xsrf = next(
                (c["value"] for c in ctx.cookies() if c["name"] == "XSRF-TOKEN"),
                None,
            )
            if not xsrf:
                fail("No XSRF-TOKEN cookie found — session likely expired. "
                     "Re-run: python3 scrape.py --login")

            resp = ctx.request.post(
                QUOTE_URL,
                data=json.dumps({"unit": QUOTE_UNIT, "value": QUOTE_VALUE}),
                headers={
                    "content-type": "application/json",
                    "accept": "application/json, text/plain, */*",
                    "x-csrf-token": xsrf,
                    "origin": "https://www.sandvik.coromant.com",
                    "referer": RECYCLING_PAGE,
                },
            )

            if not resp.ok:
                fail(f"Quote request returned HTTP {resp.status}. "
                     "Session may be expired or blocked. Re-run with --login.")

            try:
                quote = resp.json()
            except Exception:
                fail("Response was not JSON (likely a login page or bot challenge). "
                     "Re-run with --login.")

            if "price" not in quote:
                fail(f"Unexpected response shape: {quote!r}")

            # The quote's "price" field is already the per-kg rate. It can vary
            # with the submitted weight, so we always quote the same QUOTE_VALUE
            # to keep readings comparable. Convert to per-lb for the page.
            quote_weight = float(quote["netWeight"]["value"])
            price_per_kg = round(float(quote["price"]), 4)
            price_per_lb = round(price_per_kg * KG_PER_LB, 4)
            now = datetime.datetime.now()

            row = {
                "date": now.date().isoformat(),
                "timestamp": now.isoformat(timespec="seconds"),
                "currency": quote.get("currency", "USD"),
                "quote_weight_kg": quote_weight,
                "price_per_kg": price_per_kg,
                "price_per_lb": price_per_lb,
            }
            save_row(row)
            print(f"{row['date']}: {price_per_kg} {row['currency']}/kg "
                  f"({price_per_lb}/lb) at {quote_weight:g}kg")
        finally:
            ctx.close()


if __name__ == "__main__":
    run(login_mode="--login" in sys.argv)
