# Samra Jewellery CRM (`samra_crm`)

Custom CRM extensions for Samra Jewellery on Odoo 19, covering clienteling,
management reporting and external integration.

## What's in here

| Path | Contents |
| --- | --- |
| `models/` | `res.partner` clienteling fields and profile data, jewellery specs on products, dashboard aggregation |
| `controllers/` | REST API for POS / accounting / e-commerce |
| `static/src/customer_360/` | Customer 360 OWL screen |
| `static/src/dashboard/` | Management dashboard OWL screen |
| `hooks.py` | Pipeline stages, lost reasons and loyalty programs, get-or-create |
| `doc/API.md` | Endpoint reference for integrators |
| `doc/REQUIREMENTS.md` | All 45 requirements mapped to actual status |

## The two screens

**Customer 360** — reached from the *Customer 360* button on any contact.
Header with tier badge, four at-a-glance stats, a purchase timeline carrying
SKU / gold weight / stone details per line, preferences, wishlist and viewed
products with thumbnails, WhatsApp thread, appointments, tickets and rewards.
Every summary element drills through to the records behind it.

**Management Dashboard** — *Samra CRM → Dashboard*. Revenue, orders and average
order value filterable by branch, date range and salesperson, plus the
seven-stage funnel, VIP composition, branch and salesperson performance, a
reactivation list and loyalty engagement.

Both are custom OWL client actions rather than Odoo list/form views, because
the composition is the deliverable. Charts are CSS elements, not a charting
library — that is what makes every mark individually clickable and keeps a
dependency out of the backend bundle.

## Recording products shown to a customer

Requirement 5 fails if capture is a form. An associate holding a tray will not
put it down to fill four fields, and a viewed-products log nobody fills in
makes reactivation and recommendations quietly wrong.

So capture is a by-product of showing. *Showing Products* on the profile opens
one input that serves both typing and a barcode scanner — a scanner is a
keyboard that finishes with Enter, and a single exact match drops straight into
the tray so the associate can keep scanning without looking up. Items
accumulate visibly; one save at the end writes them all. Date and branch are
taken from the clock and the user's warehouse rather than asked for. *Log + add
to wishlist* handles the natural escalation without a second screen.

## Loyalty earning rate

Samra Rewards grants **0.1 points per AED**, i.e. 1 point per AED 10. An
earlier version granted 1 point per AED 1 by reading `minimum_amount` as a
divisor when it is an order qualification threshold. The hook only creates the
program when absent, so an instance that already has it keeps the old rate —
correct it by hand. Re-rating already-issued balances is a commercial decision,
not a migration.

## Customer metrics and tiering

A nightly cron recomputes lifetime value, purchase frequency and last purchase
date from confirmed orders, then re-tiers customers against thresholds held in
system parameters (`samra_crm.vip_threshold`, `samra_crm.vvip_threshold`,
defaulting to AED 100,000 and AED 300,000).

These are stored fields on a schedule rather than computed fields with a
`depends` on order history: otherwise every confirmation, invoice and POS line
would invalidate the partner record and the recompute cost would land on the
till during trading hours.

**Before the first run**, tick *VIP Tier Set Manually* on any customer whose
tier was assigned by hand — otherwise the cron will reassign them on spend.

## Known gaps

`doc/REQUIREMENTS.md` has the full picture. The ones still open:

- **No record rules.** Every internal user sees every branch's customers. Note
  this pulls against requirement 22 (one central customer database), so the fix
  is ownership-aware write access, not branch-scoped visibility.
- **Consent is enforced at the audience, not at the send.** A hand-written
  domain in Email Marketing still reaches anyone.
- **Deletions and discount overrides are not audited.** Transfers now are.
- **No WhatsApp connector.** The log records; nothing sends.

## Validation status

Python compiles, JavaScript parses, XML is well-formed. **None of this has been
executed** — no Odoo instance was available when it was written. It needs a
staging build before it goes anywhere near production.
