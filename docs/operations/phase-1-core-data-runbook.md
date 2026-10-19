---
title: Phase 1 core data and control app runbook
summary: The runbook that built Phase 1 (data model, pricebook and pricing engine, Baserow import, control app) as executed from 2026-10-14 to 2026-10-18, kept as a historical record.
audience: [owner, developer]
visibility: restricted
status: historical
updated: 2026-10-18
tags: [phase-1, runbook, history]
related: [docs/overview/roadmap.md, data/phases.yaml, docs/operations/phase-0-foundations-runbook.md]
---

> Historical record. This runbook was kept as a working document in the Claude app during Phase 1 and copied here when the phase closed on 2026-10-18. The task prompts are as they were given to Claude Code. The plan review of 2026-10-17 is recorded in decisions 0056 to 0062. For how things work now, follow the reference and operations docs, not this page.

# Phase 1 core data and control app runbook

Oct 14, 2026 · @Kris Grassman

**Progress on 2026-10-14:** Phase 0 is closed; the restore test passed after a fix to how it counted tables. Steps 1 and 2 are merged, including the follow-ups for gift cards and vouchers (0054), helper pay types and flexible vehicle classes. Step 3 prep is done as well: the plan review merged on 2026-10-17 as pull request #18, with decisions 0056 to 0062 (0055, rounding percentage promotions to the cent, came from Step 2). Next: Step 3.

**Plan review before Step 3 (finished 2026-10-17):** ten items agreed in Plan review. They go to Claude Code as one pull request in Step 3 prep, below.

## What Phase 1 delivers

Phase 1 turns the empty server into a working back office: the whole database, the pricebook loaded from your price matrix, the first control app screens, and every Baserow record imported. It is done when the pricebook in the app matches the price matrix cell for cell and your imported job history is searchable.

What gets built:

- **The data model for all nine areas** (customers, appointments, pricebook, billing, history, promotions, staff, bookkeeping, marketing), so later phases add screens without restructuring stored data.
- **The pricing engine:** one piece of code that builds every estimate from the pricebook, tested against your rules and the RAV4 example.
- **Pricebook versions:** edits are drafts you publish with an effective date, and booked jobs keep their own copy of their prices.
- **The control app's first screens:** sign-in, customers, vehicles, appointments and the pricebook, installable on the Pixel.
- **The importer** for Baserow and Setmore, safe to run again with fresh exports just before launch.
- **Documentation:** the data model page becomes current, and the first guides are written.

| Step | You | Claude Code, in the repo |
| --- | --- | --- |
| Before you start | Merge the docs pull request, close Phase 0 | Run migrations on start |
| 1. Development setup | Approve the setup | Local test database, automated tests on GitHub |
| 2. Data model | Review the plain-language model | Models, migrations, change history, updated docs |
| 3 prep. Plan review | Unzip the package, review the pull request | The ten agreed changes in docs and data, new decisions |
| 3. Pricebook | Check the prices against your spreadsheet | Pricebook load, pricing engine, quote record, versioned publishing |
| 4. Import | Copy fresh exports to the server, read the dry-run report | Importer with a dry run and a report |
| 5. Control app | Create your login, try the screens on the Pixel with your real records | Sign-in, customers, vehicles, appointments, staff, pricebook screens |
| 6. Acceptance | Run the done test, read the guides | First guides, docs status updates |

Each step runs the loop you know from Phase 0: give Claude Code the task, read and merge its pull request, pull to the server, run the check. The tasks below are short because they point Claude Code at the repo docs, which already hold the rules.

## Before you start: close Phase 0

Three loose ends from Phase 0 come first, because everything in Phase 1 builds on them. Before every task below, start from an up-to-date `main` on the Fedora machine: `git switch main && git pull`.

1. **Merge the docs pull request.** If Claude Code's docs migration pull request is still open, read its list of places where the docs had drifted from the code, then merge it. The repo should now have `docs/README.md`, and `DOCS-MIGRATION.md` should be gone.
2. **Pull it to the server and restart the stack**, because that pull request also added `BWS_SERVER_URL` to the start script. Use the routine in `docs/operations/deploying-changes.md`, then check `curl http://127.0.0.1:8000/health`.
3. **Make migrations run on every start.** Give Claude Code this task:

> Make the app container run `python manage.py migrate --noinput` on every start, before the web server starts, so the database always matches the code. Update docs/architecture/server-and-stack.md, and remove this carry-over from docs/overview/roadmap.md and data/phases.yaml. Open a pull request.

4. **Merge, pull and restart,** then check the app log for the migrate step. `showmigrations` prints nothing at this point, which is expected: the Phase 0 app has no database tables yet, so there is nothing to list.
5. **The deferred restore test moves to the end of Step 2.** It checks that Django's tables come back from a backup, and the first tables arrive with the data model.

```bash
cd /srv/dixie-detail
docker compose logs --tail 40 app | grep -iE "migrat|error"
```

**Check:** the docs pull request is merged, and the app log shows the migrate step running at start (for example "No migrations to apply") with no errors.

## Decisions this phase makes

Phase 1 fixes eight technical choices that every later phase lives with. Each has a default, and Claude Code records all eight as decision records 0045 to 0052 in Step 1. One of them changes a rule you set; you approved it on 2026-10-14.

| Choice | Default | Why |
| --- | --- | --- |
| **Development values (approved 2026-10-14)** | Local development and the GitHub tests use made-up throwaway values kept in a development-only file. No Bitwarden on the workstation | Throwaway values protect nothing, so they are not secrets. This replaces the CLAUDE.md rule asking for a second Bitwarden project and token on Fedora |
| Control app screens | Django pages with htmx: server-built, mobile-first, installable on the Pixel. Django's admin stays as an owner-only back door | One Python codebase with almost no JavaScript, fast on a phone, simple for Claude Code to keep up |
| Money | Exact dollars and cents, never floating point; rounding as in `data/pricing-rules.yaml` | Floating point drifts by fractions of a cent |
| Time | Stored in UTC, shown in Eastern; a job's date is its Eastern calendar date | Avoids the UTC mix-up Baserow had |
| Phone numbers | Stored as 10 digits, shown as (###) ###-#### | Quiet matching compares digits only |
| Change history | The django-simple-history library on the pricebook, customers, vehicles and appointments | Records who changed what, when and the old value, so a change can be undone |
| Re-runnable import | Imported records keep their Baserow id, so the importer can update them; the final run uses fresh exports just before launch | Baserow keeps changing until launch |
| Sign-in | Django accounts. Your password lives in your Bitwarden vault, and Tailscale already limits who can reach the sign-in page | Simple now; two-factor sign-in can be added when staff join |

Step 2 adds two more: decision 0053 for checks and trades as owner-only payment methods, and 0054 for gift cards and promotional vouchers. The alternative to htmx, a separate JavaScript app (React or Vue), adds a second toolchain for little gain at this size.

## Step 1: Development setup and automated tests

From here on Claude Code writes real business logic, so every pull request needs tests that run by themselves on your workstation and on GitHub. Fedora ships Podman rather than Docker, and the setup uses it for a throwaway test database.

1. Give Claude Code this task:

> Set up development and automated tests for Phase 1. Tests must run the same way on this Fedora workstation (Podman, not Docker) and on GitHub Actions, against a throwaway PostgreSQL 18 database, using made-up development values in a development-only settings file that production can never load. Update the development rule in CLAUDE.md, and record these Phase 1 conventions as decision records: 0045 development uses made-up throwaway values, not Bitwarden; 0046 control app screens are Django pages with htmx, mobile-first and installable, with Django admin for superusers only; 0047 money is stored as exact decimals, never floating point; 0048 times are stored in UTC and shown in Eastern; 0049 phone numbers are stored as 10 digits; 0050 django-simple-history records changes to the pricebook, customers, vehicles and appointments; 0051 imported records keep their Baserow ids so the import can be re-run before launch; 0052 Django sign-in, reachable only over Tailscale. Add one command to run the tests locally, a GitHub Actions workflow that runs them on every pull request, pytest with Django, and a test for the existing /health page. Update docs/operations/workstation-setup.md and data/configuration.yaml. Also fix this error the app logs at every start, without loosening the container's read-only file system: gunicorn's "Control server error: \[Errno 30\] Read-only file system: '/home/app'". Either turn off gunicorn's control server or point it at the container's writable temporary space, and add the fix to docs/operations/troubleshooting.md. Tell me anything I need to install with dnf. Open a pull request.

2. Install whatever it lists with `sudo dnf install -y …`, then run its test command once on the Fedora machine.
3. Read and merge the pull request. Nothing changes on the server in this step, so there is no pull or restart.

From now on, every pull request shows two checks on GitHub, Docs and Tests. Never merge one with a red check; ask Claude Code to fix it first. (GitHub can enforce this only on paid plans for private repositories, so it is a habit, not a lock.)

**Check:** the local test command passes, and the pull request showed both checks green before you merged it.

## Step 2: The data model

The data model is the one piece that is expensive to change later, so it covers all nine areas now and you review it in plain language before anything is built on it. The design is already in `docs/architecture/data-model.md`. Your Baserow export adds a few things it must hold, named in the task.

1. Give Claude Code this task:

> Build the Phase 1 data model described in docs/architecture/data-model.md, covering all nine areas, as Django apps with migrations. Follow decisions 0033 (pricebook versions and line snapshots), 0034 (quiet matching) and 0035 (GnuCash mapping), and the conventions recorded from 0045 onward. The Baserow export shows the model must also hold: several services on one appointment (a main service plus add-ons), helpers assigned to a job with a flat pay amount per job, named promotions (such as Friends & Family, Multi-Vehicle and seasonal offers), a final price that differs from the list price with a reason, gift cards sold as a dollar balance with a code, the buyer and an optional recipient, held as money owed until used and usable across several jobs (the imported gift-card job stays a simple prepayment), free promotional vouchers as a kind of promotion with a code and a dollar value, payments by check and payments split across two methods, tips (including a short payment recorded as a negative tip), jobs given at no charge as a gift with a reason, jobs paid in goods instead of money (a trade, recording the goods and their value), promotions defined as a percentage off or a fixed price, helper pay that can be overridden per job, and vehicles with a missing year, model or seat rows. Add check and trade as owner-only payment methods, accepted case by case and never offered on the website, and record that as decision 0053. Update docs/reference/payments.md, data/business.yaml and data/gnucash-accounts.yaml: a check posts to Assets:Current Assets:Checking Account as a direct deposit; a trade records what was received and its value, and is left out of the GnuCash export and listed for manual entry, like bitcoin; each helper has a pay type, family helper or employee; family helper pay posts to the owner's Professional Services expense account (assume Expenses:Professional Services and ask me to confirm the full name in the pull request), on the owner's accountant's advice about paying family members, and is not a rule for every helper; employee wages through payroll are a later decision with no account yet. Record gift cards and vouchers as decision 0054, and add their postings to data/gnucash-accounts.yaml and docs/reference/bookkeeping-gnucash.md: a gift card sale debits the payment account and credits Liabilities:Gift Cards Outstanding with the whole amount, tax included, and posts no sales tax; using a card debits Liabilities:Gift Cards Outstanding and credits Income:Detailing Services and Liabilities:Sales Tax Payable as for any paid job; a voucher posts nothing when given and its value to Income:Discounts & Refunds when used. Make vehicle classes and their size variants records, not fixed choices in code, so a class can be added, renamed or retired with no code change or migration, and allow a class with a single price and no size variant (for a possible motorcycle class); each line snapshot also keeps the class and size variant as booked. Add change history as decided. Write tests for the key rules: a booked appointment's line snapshot never changes when the pricebook does, and phone numbers are stored as 10 digits. Then rewrite docs/architecture/data-model.md from the code with status current, a Mermaid diagram of the main records and a plain-language description of each, and add any new terms to the glossary. Open a pull request.

2. **Review the model before merging.** Open `docs/architecture/data-model.md` in the pull request on GitHub, which draws the diagram. Check that everything your business handles has a home. Questions worth asking yourself:
   - Do you sell gift cards that sit unused for a while, or are they always tied to a booked job?
   - How are helpers paid: always a flat amount per job, or sometimes hourly?
   - Does anything you track in Baserow notes today deserve its own field?
3. Ask Claude Code for any changes in the same pull request, then merge it, pull to the server and restart the stack. The new tables are created on start.

**Check:** `docker compose exec app python manage.py showmigrations` lists every migration with `[X]`. Then run a backup and the restore test deferred from Phase 0: `sudo systemctl start dixie-backup.service`, then `sudo /srv/dixie-detail/ops/restore-test.sh`. It should report the new tables and pass, which closes Phase 0.

## Step 3 prep: Apply the plan review

The ten items agreed in the Plan review tab go into the repo as one pull request of docs and data before Step 3, because Step 3 loads the new service hours. The package is plan-review-2026-10-17.zip, sent in our conversation on 2026-10-17: instructions for Claude Code and the updated price matrix (the same 90 prices; the hours are now service time).

1. On the Fedora workstation, unzip the package at the top of the repo:

```bash
cd ~/Projects/Dixie-Detail
git switch main && git pull
unzip ~/Downloads/plan-review-2026-10-17.zip
```

2. Give Claude Code this task:

> Apply plan-review-2026-10-17/PLAN-REVIEW.md: follow its instructions in one branch and one pull request, and delete the plan-review-2026-10-17 folder in that pull request.

3. Read the pull request description. It lists the new decisions, the price check (90 rows, identical prices) and any names left for Step 3 to rename. Merge, clean up the branch, and pull on the server. Nothing needs a restart, since only docs and data change.

**Check:** the Docs check passed on the pull request, and data/price-matrix.csv on main has the column one\_person\_service\_hours. Done 2026-10-17: pull request #18, decisions 0056 to 0062.

## Side task: Public portfolio copy

The working repo goes back to private, and a separate public copy, rewritten so it never contains server addresses or private details, becomes your portfolio (decision 0063). Two packages were sent on 2026-10-17: portfolio-setup-2026-10-17.zip goes into the repo through Claude Code, and portfolio-private-config.zip stays on your workstation, never in a repo. Once merged, the full procedure, including what to do when the script stops, is in docs/operations/publishing-the-portfolio.md.

1. On GitHub, check the fork count on Dixie-Detail, then make it private: Settings, General, Danger Zone, Change repository visibility, Private.
2. Create an empty public repository named Dixie-Detail-portfolio (done 2026-10-17: https://github.com/UninterestingUser/Dixie-Detail-portfolio), with no README, license or .gitignore.
3. In GitHub Settings, Emails, turn on "Keep my email addresses private" and copy the no-reply address it shows.
4. On the Fedora workstation, install the tool and put the private settings in place:

```bash
sudo dnf install git-filter-repo
mkdir -p "$HOME/Dixie Detail/github-portfolio"
unzip ~/Downloads/portfolio-private-config.zip -d "$HOME/Dixie Detail/github-portfolio"
chmod 600 "$HOME/Dixie Detail/github-portfolio"/*
git config --global user.email "YOUR-NO-REPLY-ADDRESS"
```

5. Edit \~/Dixie Detail/github-portfolio/mailmap and put your no-reply address where it says REPLACE-WITH-YOUR-GITHUB-NO-REPLY-ADDRESS. If you named the public repository differently, change public-url too.
6. Unzip the setup package at the top of the repo:

```bash
cd ~/Projects/Dixie-Detail
git switch main && git pull
unzip ~/Downloads/portfolio-setup-2026-10-17.zip
```

7. Give Claude Code this task:

> Apply portfolio-setup-2026-10-17/PORTFOLIO-SETUP.md: follow its instructions in one branch and one pull request. Do not commit the portfolio-setup-2026-10-17 folder; delete it when you're done. One change to those files: the settings folder is \~/Dixie Detail/github-portfolio (with a space), not \~/Dixie-Private/portfolio. Make that the default in tools/publish-portfolio.sh and use it in docs/operations/publishing-the-portfolio.md and decision 0063, and keep every use of the path quoted so the space works.

8. Read the new README in the pull request, merge, and clean up the branch. Then publish:

```bash
git switch main && git pull
tools/publish-portfolio.sh --dry-run
tools/publish-portfolio.sh
```

9. On the public repository: turn on Dependabot alerts, secret scanning and push protection; add a ruleset for main that restricts deletions and blocks force pushes; fill in About; and pin it on your profile.

**Each update,** for example at the end of a phase: `cd ~/Projects/Dixie-Detail && git switch main && git pull && tools/publish-portfolio.sh`. Read the review list (the business phone number always appears) and the new commit titles before answering y.

**Check:** the public repository shows the full history under your name with the no-reply address, and searching it for your server's network address or tailnet name finds nothing.

## Step 3: Pricebook and pricing engine

Every price the system will ever show comes from one pricing engine reading one pricebook, so this step is mostly tests: the 90 prices, your rules and the RAV4 example must all come out exactly right before any screen shows them.

1. Give Claude Code this task:

> Load the pricebook and build the pricing engine, following decisions 0055 to 0062 (promotion rounding and the plan review). A management command, load\_pricebook, loads data/price-matrix.csv (its hours are one-person service hours, without setup and breakdown), data/services.yaml and data/pricing-rules.yaml into the database as pricebook version 1, effective today; running it again changes nothing. The pricing engine is one module that takes a service, vehicle class, size variant, condition level, add-ons, promotions and crew size, and returns the priced lines, the total before tax and the service time, exactly as docs/reference/pricing.md describes. Structure it so a vehicle class could later use another price basis, such as per foot of length, without reworking the rest; build only the fixed price list now. Add a time-on-site function that adds setup and breakdown, divided by the number of people, to the service time, reading the launch values from data/booking-rules.yaml until Phase 3 adds the settings screen. Add the quote record from the price-of-record decision: a server-issued quote with its inputs, lines, totals, pricebook version, tax rate, service time and time on site, whose lines become an appointment's line snapshot when it is booked. Sales tax is zero until Phase 3. Add pricebook versioning as in docs/reference/pricebook-changes.md: drafts, publishing with an effective date, and a function that lists the booked jobs a publish would affect. Add a quote command so I can price a job from the terminal; it prints the lines, the total, the service time and the time on site. Tests: all 90 cells of price-matrix.csv match the database; the RAV4 example in data/pricing-rules.yaml totals $355 with 6.5 hours of service and 7.5 hours on site; Monthly Maintenance with two people takes 2.25 to 4.5 hours on site; Headlight Restoration takes 2.5 hours on site for one person; the full-day flag starts at 8 hours on site for one person; condition never changes add-ons; a missing combination cannot be priced; maintenance follows a changed Full Detail price; an appointment booked from a quote keeps the quote's lines exactly. Rename any names the plan-review pull request left for this step. Update the docs this changes. Also, in docs/operations/publishing-the-portfolio.md, the mailmap now has two lines: "Kris Grassman \<no-reply address>", which gives every commit made with the no-reply address the owner's full name whatever name it was made under, and the existing line mapping the old personal email. Update the settings table to say so, and use https://github.com/UninterestingUser/Dixie-Detail-portfolio.git as the example public URL. Open a pull request.

2. Merge it, then run sudo /srv/dixie-detail/ops/deploy.sh on the server (it pulls, rebuilds and restarts). Then load the pricebook once:

```bash
cd /srv/dixie-detail
docker compose exec app python manage.py load_pricebook
```

3. Try a few quotes with the command Claude Code describes in the pull request, for jobs you know the price of. Start with the RAV4: Crossovers & Wagons, 2 rows, Full Detail, condition level 2, plus Seat Extraction.

**Check:** the Tests check passed on the pull request, and the RAV4 quote on the server says $355, 6.5 hours of service and 7.5 hours on site.

**Step 3 follow-up (2026-10-17): condition level lengthens the job.** You confirmed that the condition percentage adds time to the main service as well as price, with the same scope as the price rule. Give Claude Code this task:

> Condition levels also lengthen the job. Change the pricing engine so the condition percentage (0%, 10% or 20%) is added to the main service's one-person service time as well as its price, for Full Detail, Interior Only and Exterior Only only; add-ons, maintenance plans, and setup and breakdown are never adjusted. The condition line carries its extra time (the base hours times the percentage, unrounded) in its line snapshot. Then add the add-on hours, apply the two-person factor, and round the service time to the nearest 15 minutes once, as now; time on site follows from that as before. If the rule is stored with the pricebook, make the change take effect without anyone re-running load\_pricebook by hand, or say in the pull request exactly what to run. Record this as a new decision (next free number) and update docs/reference/pricing.md, data/pricing-rules.yaml (the condition levels and the worked example), docs/reference/booking-flow.md where it describes the estimate card's time, and the glossary if it defines condition level. Tests: the RAV4 example (Full Detail at level 2 plus Seat Extraction) stays $355 and becomes 7 hours of service and 8 hours on site, so the full-day flag is set; a 2-door Coupes & Sedans Full Detail at level 3 is 3.5 hours of service and 4.5 on site; a two-person 2-row Midsize SUV Full Detail at level 3 is 4 hours of service and 4.5 on site; level 1 changes nothing; add-ons and maintenance plans never change with condition. Existing quotes and appointment snapshots are not changed. Open a pull request.

Merge it, run sudo /srv/dixie-detail/ops/deploy.sh, and run anything the pull request says to. **Check:** the RAV4 quote now says $355, 7 hours of service, 8 hours on site and full day.

## Step 4: Import your Baserow and Setmore records

The importer brings in every customer, vehicle and job from Baserow, plus the Setmore contacts the migration rules keep. It runs a dry run first that changes nothing and prints a report you read before anything is written. It will run again with fresh exports just before launch, so it updates records instead of duplicating them.

Your exports and the corrections list hold personal data, so they never go in the repo. Keep them in a private folder on the Fedora machine, such as `~/Dixie Detail/imports/`. The corrections we agreed on (spellings, merges, second contacts, the gift-card prepayment, address fixes) are in **import-corrections.yaml**, which I'm sending with this runbook. Save it in that folder.

1. Give Claude Code this task:

> Build the Baserow and Setmore importer described in docs/reference/data-migration.md and decisions 0036 and 0051, as a management command that reads a folder of export files mounted read-only into a one-off app container on the server. Find each file by the table name in its file name, because Baserow's names vary ("export - Customers.csv" or "BaserowExport - Customers - Grid.csv"). The tables and their columns are: Customers (id, Name, First Name, Last Name, Phone, Email, Address, City, State, ZIP, Vehicles, Created on, Last modified, Autonumber, Appointments); Vehicles (id, Vehicle, Year, Make, Model, Vehicle Type, Seating, Color, Customer, Appointments); Appointments (id, Appointment, Date, Status, Customer, Vehicle, Vehicle Type, Service Name, Service Summary, Promo Price, List Price, Promotion, Promo Type, Promo Value, Price Override, Final Price, Notes, Bookkeeping, Hours, Staff, Auto Promo, Wages Due, Employees Paid, Job Wage Rate, Total Wages); Bookkeeping (id, Name, Appointment, Invoice, Customer Paid, Tip, Payment Method, Date, Customer, Staff, Wages Due, Wage Override, Profit); SetmoreContacts.csv (Name, Email, Email1, Phone, Phone1, Company, Address, Notes); and import-corrections.yaml, whose format is described in its own header. Formats: links between tables are display strings such as "First Last - 4235551234"; an appointment's Bookkeeping value equals exactly one Bookkeeping row's Name; Service Name is "Class - Service (N Rows)" with add-ons separated by commas, where Interior Detail means Interior Only and Exterior Detail means Exterior Only; Seating is like "2 Rows"; money is like "$1,234" and a negative tip is written '-$5; Date is MM/DD/YYYY hh:mm AM in UTC and must be stored correctly for Eastern; Hours is h:mm and is the job's whole time on site, setup and breakdown included; Staff and Payment Method can list two values separated by a comma. Payments, tips and payment methods come from Bookkeeping; a payment listing two methods is one payment recorded as split between them. Imported payments are already in the owner's GnuCash books, so mark them so the Phase 6 export never sends them again. The default is a dry run that changes nothing and prints a report: counts of each kind, every correction applied, and every row it could not place and why. A --apply flag writes, keyed on the Baserow ids so a later run with fresh exports updates rather than duplicates. Test with invented rows in these exact formats; never put real customer data in the repo. Write the run procedure in docs/operations/, update docs/reference/data-migration.md, and add the import folder path to data/configuration.yaml. Open a pull request.

2. Merge it, pull to the server and restart.
3. **Take fresh exports:** the four Baserow tables (Customers, Vehicles, Appointments, Bookkeeping) as CSV and the Setmore contact list, saved with `import-corrections.yaml` in a new dated folder under `~/Dixie Detail/imports/`.
4. **Copy them to the server** into a folder only you can read. Replace USER with your server user name:

```bash
ssh -t USER@192.0.2.10 'sudo install -d -m 700 -o USER /srv/dixie-import'
scp "$HOME/Dixie Detail/imports/2026-10-XX/"* USER@192.0.2.10:/srv/dixie-import/
```

5. **Run the dry run** with the command from Claude Code's procedure, and read the report. Compare its counts with your own sense of the business. On the 2026-10-14 exports they were 104 customers, 128 vehicles, 185 appointments (175 completed, 10 booked), 180 payment records and 4 second contacts; fresh exports will be a little higher. Expect two motorcycles with no vehicle class.
6. **Apply it** once the report looks right, then delete the copies on the server: `rm /srv/dixie-import/*`. The records now live in the database, which the nightly backup encrypts.

**Check:** the report shows no unplaced rows you can't explain, and the booked jobs come through at their Eastern times (for example, a 3:30 PM UTC entry lands at 11:30 AM).

## Step 5 prep: US spelling and identical vehicles

Two small changes you asked for on 2026-10-18 go in one pull request before Step 5: US spelling everywhere, and a rule for telling a customer's identical vehicles apart on website bookings. Give Claude Code this task:

> Two small changes in one pull request. 1. US English. The owner writes US English. Change every British spelling in the repository to US spelling: docs, data files, code comments, user-facing text, test names and the pull request template. Known cases: color or colors to color or colors, behavior to behavior, canceled and canceling to canceled and canceling, catalogue to catalog, labelled to labeled, recognised to recognized, authorise to authorize, honour to honor, judgement to judgment, grayed to grayed, initialisation to initialization; search for any others. The appointment status stored as "canceled" becomes "canceled" (label "Canceled"), with a migration that converts any existing rows; check the importer and anything else that maps statuses. Do not change third-party names, commands or library identifiers. Add "Write in US English" to docs/CONVENTIONS.md and CLAUDE.md. 2. Telling identical vehicles apart, planned for Phase 3: the booking form's vehicle step gets an optional Color box. When the matched customer has more than one vehicle with the same make, model and year, the color picks the right one; if the color is blank or matches none of them, the appointment still books and the control app asks the owner which vehicle it was, using the same flag as other differences. Color never affects the price. 3. In docs/guides/installing-the-control-app.md, say how to find the control app's address without writing it out: it is the tailnet name in DJANGO\_ALLOWED\_HOSTS in the server's .env, and \`tailscale serve status\` on the server prints it; Tailscale must be on. Write the color rule into docs/reference/returning-customers.md and docs/reference/booking-flow.md and record it as a new decision (next free number). Run python3 tools/check\_docs.py and the tests. Open a pull request.

Merge it and run sudo /srv/dixie-detail/ops/deploy.sh; the restart applies the status migration. **Check:** the pull request lists every spelling it changed, and the Tests and Docs checks passed.

## Step 5: The control app screens

The screens come in two pull requests: first sign-in and customers, then appointments and the pricebook. With your records already imported, you review each one against real customers and jobs.

**5a. Sign-in and customers.** Give Claude Code this task:

> Build the control app shell and the customer screens as Django pages with htmx (decision 0046), mobile-first, with navigation that works one-handed on a phone, the brand colors from data/business.yaml, and a web app manifest so the Pixel can install it from https://server.example-tailnet.ts.net. Sign-in must work over that HTTPS address behind Caddy and tailscale serve, including trusted origins and secure cookies. Screens: search customers by name or by phone in any format; a customer page with contact details, second contacts, addresses, vehicles, notes and every appointment with its price and payment; adding and editing customers and vehicles. Show each vehicle's color wherever vehicles are listed or picked, as in "2019 Honda Accord, silver", so a customer's identical vehicles can be told apart. Restrict Django's admin to superusers. Test the search and that every screen loads. Write the guides docs/guides/finding-a-customer.md and docs/guides/installing-the-control-app.md with status current, and update docs/reference/control-app.md. Open a pull request.

Merge, pull and restart, then create your owner login. Generate the password in your Bitwarden vault first, and paste it when asked:

```bash
cd /srv/dixie-detail
docker compose exec app python manage.py createsuperuser
```

Sign in on the Fedora machine and on the Pixel, and install the app on the Pixel by following the new guide. Look up three customers you know well, by name and by phone.

**5b. Appointments and pricebook.** Give Claude Code this task:

> Build the appointment, staff and pricebook screens. Appointments: a day and a week list; creating and editing an appointment for a customer and vehicle, with the price built live by the pricing engine as services, add-ons, condition and crew change, showing both the service time and the time on site; maintenance plans booked as a single visit or a repeating series; status booked, completed or canceled; and the final price with an on-site adjustment and its reason. The owner can book any date; availability rules arrive in Phase 3. Staff, as in the staff-authorization decision: a staff page with each person's services as toggles and a service page with each service's staff as toggles, both editing the same authorization record; managers are authorized for every service, and a new service starts with only managers authorized. On each appointment, an assign-staff control that lists qualified staff first and grays out the rest with the services they lack; accepts a two-person crew whose authorizations together cover every service; lets a manager assign someone not yet authorized, for training, after a warning and with a reason; recalculates the time on site when the crew size differs from the service's default and warns if the job now overlaps another that day; and assigns automatically when exactly one active staff member is qualified (a setting, on by default). Pricebook: prices by service and vehicle class laid out like data/price-matrix.csv; editing as a draft; publishing with an effective date; and the affected-jobs screen from docs/reference/pricebook-changes.md, with every choice logged. Test each. Write docs/guides/booking-a-job.md, docs/guides/assigning-staff.md and docs/guides/editing-the-pricebook.md with status current, and update the reference docs this touches. Open a pull request.

Merge, pull and restart, then try it: book a made-up job for yourself, change its price with a reason, and cancel it. In the pricebook, make a draft change and look at the affected-jobs screen, then discard the draft without publishing.

**Check:** the app is installed on the Pixel, the three customers show their full history, and a test job prices the same as your own math.

## Step 6: Acceptance and closing the phase

You run the done test yourself. Until launch, keep running the business in Setmore and Baserow as you do today: the control app holds a copy for checking, and the import runs again with fresh exports just before launch. New jobs entered only in the control app would be lost or duplicated by that final import.

1. **Check the pricebook against your price matrix.** Open the pricebook screen next to your Price\_Matrix spreadsheet and compare every cell, remembering the two changes we agreed on 2026-10-07: the new three-row Crossovers & Wagons prices, and Monthly Maintenance hours stored as one-person hours. Since the 2026-10-17 plan review, the hours are also service time only: an hour less than your spreadsheet for every main service, add-ons unchanged, and Headlight Restoration at 1.5 hours. The automated test already proved the database matches the repo's copy; your check proves that copy is what you meant.
2. **Search the imported history.** Pick five customers at random in Baserow and find each one in the app by name and by phone. Their vehicles, jobs, prices charged and promotions should match. Then check that every booked job is there at the right date and time, and that the gift-card job shows as paid.
3. **Run the restore test with real data:** `sudo systemctl start dixie-backup.service`, then `sudo /srv/dixie-detail/ops/restore-test.sh`.
4. **Close the phase in the docs.** Give Claude Code this task:

> Phase 1 is complete. Mark Phase 1 done and Phase 2 next in docs/overview/roadmap.md and data/phases.yaml, check that every doc changed this phase has the right status and no planned feature is described as built, run tools/check\_docs.py, and open a pull request.

### Done check

- [x] The Phase 0 restore test passed.
- [x] Decisions 0045 to 0052 are recorded in the repo.
- [x] Tests run on the Fedora machine and on GitHub, and every merged pull request had green checks.
- [x] You reviewed `docs/architecture/data-model.md`, and it is marked current.
- [x] The pricebook in the app matches your price matrix cell for cell.
- [x] The RAV4 example prices at $355, with 7 hours of service and 8 hours on site (a full day, since condition level 2 adds 10% to the Full Detail's time).
- [x] Five random customers and every booked job check out against Baserow.
- [x] The control app is installed on the Pixel, and your login password is in your Bitwarden vault.
- [x] The export copies are deleted from the server.
- [x] The restore test passes with real data.
- [x] The four guides exist: installing the app, finding a customer, booking a job, editing the pricebook.
- [ ] The roadmap shows Phase 1 done.

## What waits for later phases

The database is built for everything now, but these features arrive later, so their tables stay empty or hold only imported history until then.

| Waits for | What | Phase |
| --- | --- | --- |
| Vehicle catalog | EPA, NHTSA and Canadian-specification lookups, editable class rules with a preview, per-model and per-vehicle overrides, the review queue. Imported vehicles keep the class Baserow gave them | 2 |
| Online booking | The website, the scheduling settings screen and availability check, sales tax, address validation, calendar sync, the assign-staff prompt for website bookings, and the quiet-matching review screen | 3 |
| Texts and payments | Quo messages, Stripe, the "paid" buttons, invoices and receipts, and the one-tap arrival and departure times. Imported jobs carry only their recorded payment state | 4 |
| Launch | The final import with fresh exports, then Setmore and WordPress switched off | 5 |
| Back office | The GnuCash export, promotion management, staff pay screens (the helper pay history is imported now) | 6 |
| Later add-on | An Android companion app that records arrival and departure automatically | Not scheduled |

Four open points need your answer before Phase 3, and none blocks Phase 1: the quarter-hour rounding for a second Monthly job (decision 0022), the accountant's view on Georgia tax (decision 0037), short descriptions in your own words for each service and condition level, which the website will show, and whether to change how vehicles are priced (a new factor beyond class, size variant and condition), which is cheapest to settle before the booking flow is built.
