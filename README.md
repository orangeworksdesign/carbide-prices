# Carbide scrap price tracker

Logs the Sandvik Coromant recycling buyback price for tungsten carbide once a day
and serves a trend page from GitHub Pages.

**How it works:** the login is behind an OIDC flow + bot-defense, so the scraper
doesn't try to log in programmatically. You log in *once* by hand in a real
browser; the session (good for ~3 weeks, and likely self-renewing) is saved to a
profile folder, and a daily headless job rides it to pull one price quote. The
result is committed to this repo; GitHub Pages renders `index.html` from the data.

```
scrape.py        # pulls the quote, appends to data/prices.json
run.sh           # cron wrapper: scrape + git commit + push
index.html       # the trend page (DRO readout + chart)
data/prices.json # the logged history
browser-profile/ # created on first --login; holds the session (DO NOT COMMIT)
```

## Where this runs

Run the **scraper on your own machine** (the Proxmox box), not on GitHub Actions —
datacenter IPs get flagged hardest by the bot-defense layer. GitHub only hosts the
repo and serves the page.

## Setup

Install Python deps and the browser engine:

```
pip install -r requirements.txt
```

```
playwright install chromium
```

Establish the session. This needs a display — run it on a desktop, or over VNC /
X-forwarding into the Proxmox box. A browser opens; log in, get to the recycling
page so you can see a price, then press Enter in the terminal:

```
python3 scrape.py --login
```

Test a headless pull (in an LXC, set `CARBIDE_NO_SANDBOX=1` first):

```
python3 scrape.py
```

You should see a line like `2026-06-14: 69.71 USD / 50kg = 1.3942/kg`.

## Keep the session secret

The `browser-profile/` folder holds your live logged-in session — treat it like a
password. It's already in `.gitignore`; never commit it. (And log out / re-login
if you ever think the profile leaked.)

## Schedule it

Make the wrapper executable:

```
chmod +x run.sh
```

Add a cron entry — daily at 6:05am here:

```
5 6 * * * /path/to/carbide-price-tracker/run.sh >> /path/to/carbide-price-tracker/cron.log 2>&1
```

If the session expires, the run exits non-zero and logs the reason; that's your
cue to re-run `python3 scrape.py --login`.

## Is the session self-renewing?

Worth checking once. Note the `.AspNetCore.Cookies` expiry in DevTools today, let
the daily job run, then check again tomorrow. If the date moved forward, expiry is
*sliding* and the daily pull keeps the session alive on its own — you'll rarely
need to re-login. If it didn't move, plan to re-login about every three weeks.

## Publish the page

Push the repo to GitHub, then in **Settings → Pages**, set the source to your
default branch, root folder. The page comes up at
`https://<user>.github.io/<repo>/` and refreshes whenever `run.sh` pushes a new
reading.
