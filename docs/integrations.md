# Integrations

Every outside service connects to the core app, never straight to the database. Keys and secrets live only in Bitwarden Secrets Manager; the rules are in [CLAUDE.md](../CLAUDE.md).

| Service | Used for | Phase | Status | Cost |
| --- | --- | --- | --- | --- |
| Cloudflare | Website hosting, Tunnel, DNS | 0 | The domain already runs through Cloudflare; confirm account access | Free plan |
| Tailscale | Private access to the control app | 0 | In use; server not yet a node | Existing |
| Bitwarden Secrets Manager | Every key, password and token | 0 | In use by the owner | Existing |
| Google Workspace Calendar | Jobs and Time Off calendars | 3 | Workspace not yet set up | Workspace plan |
| Google Maps Platform | Address suggestions, traffic-aware drive times | 3 | Billing account approved, not created | Expected inside the free monthly allowance |
| Census Bureau geocoder | Address to coordinates for sales tax | 3 | Not started | Free |
| Tennessee Department of Revenue | Tax rates and boundaries, updated quarterly | 3 | Not started | Free |
| EPA FuelEconomy.gov | Year, make, model and size class | 2 | Not started | Free |
| NHTSA vPIC | Makes and models the EPA leaves out, door and seat data | 2 | Not started | Free |
| Quo | Calls, owner texts, automated texts | 3 to 4 | Account open; registration waits for the new booking form; number not ported | Monthly plan, plus $0.01 per automated text segment |
| Stripe | Card payment links, Tap to Pay, Cash App Pay | 4 | Confirm account is in the business's name | Per transaction |
| GnuCash | General ledger, fed by a multi-split CSV export | 6 | Need account names | Free |
| BTCPay Server | Bitcoin invoices | 7 | Deferred | Free, self-hosted |

## Notes

- **Quo:** the core app sends texts through Quo's API and receives replies by webhook. Before relying on the plan you choose, confirm in Quo that API keys and webhooks are available on it. Registration status and rules are in [compliance.md](compliance.md).
- **Stripe:** payment links and Cash App Pay report back automatically. Tap to Pay payments taken in the Stripe Dashboard app are matched by amount and time, then confirmed with one tap.
- **Venmo, PayPal and cash:** recorded with a one-tap "paid" button. PayPal Checkout could automate PayPal and Venmo later.
- **GnuCash:** each completed job becomes one balanced transaction: the payment account debited, income credited by service, and Sales Tax Payable credited. Stripe fees and payouts get their own transactions. The owner imports a date range with a saved CSV preset.
- **Google:** one Google Cloud project holds the service account for the calendars and the Maps key. The service account's JSON key and the server-side Maps key are stored in Bitwarden and read into memory when the app starts; there is no key file on disk. The Maps key used by the website's address field is public by design, so it is restricted to dixiedetail.com and the Maps services it needs.
