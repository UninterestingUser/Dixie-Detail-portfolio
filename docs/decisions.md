# Decisions

Every settled decision, newest last. When a rule changes, add a new row instead of editing the old one, and say which row it replaces.

| # | Date | Area | Decision | Reason |
| --- | --- | --- | --- | --- |
| 1 | 2026-10-07 | Stack | PostgreSQL plus Django for the database, API and control app | Built-in admin, logins and migrations cover most of a back-office app |
| 2 | 2026-10-07 | Stack | Astro static site on Cloudflare's free plan | Fast, SEO-friendly, and stays up when the home server is down |
| 3 | 2026-10-07 | Scheduling | Build scheduling into the core app and retire Setmore | Keeps services, durations and availability in one database |
| 4 | 2026-10-07 | Hosting | Business data on the owner's home server | Owner's preference, at no added cost. Move to a cloud server if outages recur |
| 5 | 2026-10-07 | Network | Private access over the existing Tailscale network; the server joins as its own node | Already in use; avoids a subnet clash on other Wi-Fi networks and gives the control app HTTPS |
| 6 | 2026-10-07 | Calendar | Google Workspace, with two calendars: Jobs (system writes) and Time Off (owner writes) | Keeps system events and owner blocks apart |
| 7 | 2026-10-07 | Phone | Quo for calls and texts; port (423) 380-9120 after carrier registration clears | One number for calls, personal texts and automated texts |
| 8 | 2026-10-07 | Payments | Stripe for cards and Cash App Pay; cash, Venmo and PayPal as a manual "paid" button | Payment is due at service, with no deposit or card on file |
| 9 | 2026-10-07 | Payments | Bitcoin moves to its own phase after launch; Lightning is decided then | Keeps BTCPay setup from delaying the project |
| 10 | 2026-10-07 | Books | GnuCash stays the general ledger, fed by a multi-split CSV export | Owner already uses it and does not want paid accounting software |
| 11 | 2026-10-07 | Pricing | The price matrix supersedes every price on the current website | Owner's updated prices |
| 12 | 2026-10-07 | Pricing | Quarterly Maintenance is 80% and Monthly Maintenance 50% of the Full Detail price, as a rule | One change to Full Detail moves both |
| 13 | 2026-10-07 | Pricing | Condition adds 0%, 10% or 20% to Full Detail, Interior Only or Exterior Only, not to add-ons, rounded to the dollar | Matches the Armstrong condition template to start |
| 14 | 2026-10-07 | Pricing | Cars are priced by doors: two doors takes the 1-row price, four doors the 2-row price | Owner prices cars by doors, not seats |
| 15 | 2026-10-07 | Pricing | Crossovers and Wagons gain a 3-row price: Full Detail $280 / 6.5 h, Interior Only $180 / 4 h | Owner's addition |
| 16 | 2026-10-07 | Booking | Derive size from the vehicle data and ask the customer only when the data cannot settle it | Customers should not guess their category |
| 17 | 2026-10-07 | Crew | Matrix hours are one-person hours; two people take 60% of the time, rounded to 15 minutes; crews are one or two people | Owner's measured figure |
| 18 | 2026-10-07 | Crew | Monthly Maintenance defaults to two people; everything else to one | The original Monthly times assumed two people |
| 19 | 2026-10-07 | Crew | Flag a second person at 8 or more one-person hours; the estimate card then shows "full day" | Long jobs are allowed, with no cap |
| 20 | 2026-10-07 | Booking | Arrival times 8:00, 8:30 or 9:00 AM for every service; closed Sundays; no same-day or next-day booking | Owner's schedule |
| 21 | 2026-10-07 | Booking | One job per day, except two Monthly Maintenance jobs; Monthly and Quarterly are booked by the owner only | Owner's schedule |
| 22 | 2026-10-07 | Booking | The second Monthly job starts at the first's scheduled end plus the drive time between them, minimum 30 minutes, rounded up to the quarter hour | Owner's rule; the rounding is a proposal still to confirm |
| 23 | 2026-10-07 | Alerts | Push a time-to-leave alert at drive time plus 10 minutes before the start | Owner's rule |
| 24 | 2026-10-07 | Maps | Google Maps Platform for address suggestions and traffic-aware drive times | Usage expected to stay inside the free monthly allowance |
| 25 | 2026-10-07 | Tax | Sales tax added on top, at the rate for the customer's service address | Owner's decision; the rule stays a single setting |
| 26 | 2026-10-08 | Texting | Submit carrier registration only when the new booking form with its consent checkboxes is public | The Setmore page cannot carry compliant consent wording |
| 27 | 2026-10-13 | Backups | Nightly dumps to the RAID, plus an encrypted restic copy in the owner's Google Workspace Drive through rclone | Storage the owner already pays for |
| 28 | 2026-10-13 | Security | Every key, password and token lives in Bitwarden Secrets Manager; nothing secret is stored in plaintext. The server keeps only the machine-account token, encrypted with systemd-creds, and fetches the rest at start | Owner's policy |
| 29 | 2026-10-13 | Backups | Back up at 2:30 AM Eastern; keep 14 daily and 12 monthly dumps, on the RAID and on Drive; ping Healthchecks on success and failure | Owner's schedule and retention; a failed or missed backup raises an alert |
