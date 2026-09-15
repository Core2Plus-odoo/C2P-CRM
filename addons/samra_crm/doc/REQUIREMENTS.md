# Samra CRM — Requirements Traceability

The 45 functional requirements, mapped to what actually exists today.

Status meanings — these are deliberately strict. "Built" means code in this
module. "Standard" means Odoo already does it with configuration, which is the
right answer and not a gap. "Partial" means the mechanism exists but something
named in the requirement does not. "Open" means nothing implements it.

| # | Requirement | Status | Where / what is missing |
|---|---|---|---|
| 1 | Customer 360° Profile | **Built** | Customer 360 OWL screen. Birthday, nationality and notes added this phase |
| 2 | Complete Purchase History | **Partial** | Timeline shows invoice, branch, salesperson, SKU, qty, price, gold weight, stone details. `x_gold_weight` / `x_stone_details` are new and **not yet populated** on the 106 variants |
| 3 | Jewellery Preferences | **Built** | Gold colour, category, collection, size, diamond spec, plus gemstone and style added this phase |
| 4 | Customer Wishlist | **Built** | `x_samra_wishlist`, shown with thumbnails; one tap from the capture panel |
| 5 | Viewed Products | **Built** | Capture panel: scan or search, tap to tray, save once. Date and branch auto-stamped |
| 6 | Customer Segmentation | **Partial** | Manual tags only. No rules engine driving spend / frequency / recency segments |
| 7 | VIP / VVIP Management | **Built** | Field, badges, dashboard composition, and nightly auto-promotion from lifetime value. `x_vip_tier_manual` pins a hand-assigned tier so the cron cannot undo it |
| 8 | Customer Lifetime Value | **Built** | Nightly `ir.cron` recomputes spend, frequency and last purchase from confirmed orders, including zeroing customers whose only order was cancelled |
| 9 | Clienteling | **Built** | The Customer 360 screen is this requirement |
| 10 | Cross-Selling & Recommendations | **Open** | Nothing recommends complementary products |
| 11 | Lead Management | **Built** | Seven stages via `hooks.py`; funnel on the dashboard |
| 12 | Follow-Up Management | **Partial** | Odoo activities cover the mechanism. No overdue/pending manager view |
| 13 | WhatsApp Integration | **Partial** | Log model and profile thread exist; the header button opens `wa.me`. **No API connector — nothing sends or receives programmatically** |
| 14 | WhatsApp Product Sharing | **Open** | Needs 13 first |
| 15 | WhatsApp Invoice Sharing | **Open** | Needs 13 first |
| 16 | Birthday & Anniversary | **Partial** | Both fields captured and shown. **No reminder automation** |
| 17 | New Collection Campaigns | **Partial** | Email Marketing and Marketing Automation are installed; targeting depends on segmentation (6) |
| 18 | Customer Reactivation | **Built** | Dashboard panel, 90-day cutoff, click through to the profile |
| 19 | Appointment Management | **Standard** | Appointment app; upcoming appointments surfaced on the profile |
| 20 | Salesperson Assignment | **Standard** | `user_id`; shown in the profile header and as a dashboard filter |
| 21 | Customer Transfer | **Built** | Manager-only transfer action with a required reason, posted to each customer's chatter. History stays with the customer — ownership changes, nothing is copied |
| 22 | Multi-Store Customer Database | **Standard** | One database, four warehouses. Inherently satisfied |
| 23 | POS Integration | **Partial** | POS is installed and shares the customer and product master. **Viewed/wishlist capture is not wired into the POS UI** — an associate working from the POS screen cannot log a showing |
| 24 | Inventory Integration | **Built** | `GET /api/samra/stock/<id>` returns per-branch on-hand, reserved and available |
| 25 | Recommendations Based on Inventory | **Open** | Needs 10 |
| 26 | Repairs & After-Sales | **Open** | Helpdesk could host this, but no repair type, workflow or warranty tracking exists |
| 27 | Quotation Management | **Standard** | Sales quotations |
| 28 | Lost Sales Tracking | **Built** | Five lost reasons via `hooks.py` |
| 29 | Customer Feedback & Complaints | **Standard** | Helpdesk; open tickets surfaced on the profile |
| 30 | Marketing Consent | **Partial** | Captured, displayed, and consented audiences available as menu actions reporting reachable vs excluded counts. Still a guard rail, not a seal: a hand-written domain in Email Marketing can reach anyone |
| 31 | Campaign Management | **Partial** | Standard apps; targeting quality depends on 6 |
| 32 | Campaign Performance | **Standard** | Marketing Automation reporting |
| 33 | Management Dashboard | **Built** | Revenue, orders, AOV, funnel, branches, reactivation, loyalty |
| 34 | Salesperson KPI Dashboard | **Partial** | Revenue, orders, average ticket per salesperson. No leads / follow-ups / conversion / repeat-customer columns |
| 35 | VIP Sales Dashboard | **Partial** | Tier composition and revenue share. No per-tier visit frequency or average spend |
| 36 | Customer Retention Reports | **Partial** | Inactive customers covered. Repeat-customer analysis not built |
| 37 | Customer Acquisition Reports | **Open** | No new-customer-by-source reporting |
| 38 | Mobile & iPad Access | **Built** | Both screens responsive to phone width; tables scroll rather than squeeze |
| 39 | Role-Based Access | **Partial** | Delete restricted to Sales managers this phase. **No record rules — every associate sees every branch's customers** |
| 40 | Audit Trail | **Partial** | `x_vip_tier` tracked; transfers now logged to chatter with actor and reason. Deletions and discount overrides still are not |
| 41 | Advanced Customer Search | **Standard** | Odoo search covers name, phone, email, reference |
| 42 | Duplicate Customer Detection | **Standard** | Contacts merge tool |
| 43 | API & System Integration | **Built** | Four REST endpoints plus XML-RPC. See `API.md` |
| 44 | Data Security & Backup | **Partial** | Odoo.sh backups; ACLs tightened. No field-level encryption or retention policy |
| 45 | Multi-Branch Reporting | **Built** | Branch filter and branch comparison on the dashboard |

**Tally:** 18 built · 6 standard · 15 partial · 6 open.

## Known gaps worth acting on first

**Requirement 39 — no record rules.** Every internal user can read every
customer in every branch. For a four-branch business with per-branch associates
that is probably wrong, and it is the sort of thing that is much cheaper to fix
before more code reads this data than after.

**Requirement 30 — consent is enforced at the audience, not at the send.**
*Marketing Audiences* builds lists filtered to consented customers and reports
how many were excluded, so the shape of the consent problem is visible. But a
marketer writing their own domain in Email Marketing still reaches anyone.
Sealing that means wiring these domains into the mailing models, which needs a
running instance to do safely.

**Requirement 13 — "WhatsApp integration" currently means a log.** The model
records messages and the profile renders them as a thread, but every entry has
to be created by hand or by a future connector. The header button opens
`wa.me`, which is a link, not an integration. Worth being precise about this in
client conversations.

**On the first run of the metrics cron, tiers will move.** Customers are
re-tiered against AED 100,000 (VIP) and AED 300,000 (VVIP), configurable in
system parameters. If tiers were assigned by hand for the demo, tick
*VIP Tier Set Manually* on those customers first, or the first nightly run will
reassign them on spend.

**Record rules and branch visibility pull against requirement 22.** Worth
stating plainly before anyone implements 39: requirement 22 wants one central
customer database where a customer is recognised at every branch, so scoping
customer *visibility* by branch would break it. What is missing is narrower —
ownership-aware write access and branch-scoped operational data — not hiding
customers from each other's branches.
