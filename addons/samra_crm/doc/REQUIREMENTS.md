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
| 7 | VIP / VVIP Management | **Partial** | Field, badges and dashboard composition exist. **Auto-promotion from lifetime value is not implemented** |
| 8 | Customer Lifetime Value | **Partial** | Fields exist and are read everywhere, but **no cron populates them**. See "Known gaps" below — this is the most load-bearing gap in the list |
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
| 21 | Customer Transfer | **Partial** | Reassigning `user_id` works. No controlled transfer action, no audit of who moved what |
| 22 | Multi-Store Customer Database | **Standard** | One database, four warehouses. Inherently satisfied |
| 23 | POS Integration | **Partial** | POS is installed and shares the customer and product master. **Viewed/wishlist capture is not wired into the POS UI** — an associate working from the POS screen cannot log a showing |
| 24 | Inventory Integration | **Built** | `GET /api/samra/stock/<id>` returns per-branch on-hand, reserved and available |
| 25 | Recommendations Based on Inventory | **Open** | Needs 10 |
| 26 | Repairs & After-Sales | **Open** | Helpdesk could host this, but no repair type, workflow or warranty tracking exists |
| 27 | Quotation Management | **Standard** | Sales quotations |
| 28 | Lost Sales Tracking | **Built** | Five lost reasons via `hooks.py` |
| 29 | Customer Feedback & Complaints | **Standard** | Helpdesk; open tickets surfaced on the profile |
| 30 | Marketing Consent | **Partial** | Captured and displayed prominently. **Not enforced** — nothing stops a campaign targeting a customer who declined |
| 31 | Campaign Management | **Partial** | Standard apps; targeting quality depends on 6 |
| 32 | Campaign Performance | **Standard** | Marketing Automation reporting |
| 33 | Management Dashboard | **Built** | Revenue, orders, AOV, funnel, branches, reactivation, loyalty |
| 34 | Salesperson KPI Dashboard | **Partial** | Revenue, orders, average ticket per salesperson. No leads / follow-ups / conversion / repeat-customer columns |
| 35 | VIP Sales Dashboard | **Partial** | Tier composition and revenue share. No per-tier visit frequency or average spend |
| 36 | Customer Retention Reports | **Partial** | Inactive customers covered. Repeat-customer analysis not built |
| 37 | Customer Acquisition Reports | **Open** | No new-customer-by-source reporting |
| 38 | Mobile & iPad Access | **Built** | Both screens responsive to phone width; tables scroll rather than squeeze |
| 39 | Role-Based Access | **Partial** | Delete restricted to Sales managers this phase. **No record rules — every associate sees every branch's customers** |
| 40 | Audit Trail | **Partial** | `x_vip_tier` is tracked. Transfers, deletions and discounts are not |
| 41 | Advanced Customer Search | **Standard** | Odoo search covers name, phone, email, reference |
| 42 | Duplicate Customer Detection | **Standard** | Contacts merge tool |
| 43 | API & System Integration | **Built** | Four REST endpoints plus XML-RPC. See `API.md` |
| 44 | Data Security & Backup | **Partial** | Odoo.sh backups; ACLs tightened. No field-level encryption or retention policy |
| 45 | Multi-Branch Reporting | **Built** | Branch filter and branch comparison on the dashboard |

**Tally:** 15 built · 6 standard · 18 partial · 6 open.

## Known gaps worth acting on first

**Requirement 8 — lifetime value has no cron.** `x_lifetime_value`,
`x_purchase_frequency` and `x_last_purchase_date` are plain stored fields with
a comment saying a scheduled action fills them. That scheduled action is not in
this module. Every figure that reads from them is therefore only as fresh as
whatever last wrote them: the profile's headline stat, VIP tiering (7), the
reactivation list (18, 36) and the dashboard's inactive count. If those numbers
were seeded once for the demo, they are drifting now. This is the single
highest-leverage thing left.

**Requirement 39 — no record rules.** Every internal user can read every
customer in every branch. For a four-branch business with per-branch associates
that is probably wrong, and it is the sort of thing that is much cheaper to fix
before more code reads this data than after.

**Requirement 30 — consent is recorded but not enforced.** The profile shows it
clearly, which is worth something, but nothing prevents a campaign from
including a customer who declined. Under UAE PDPL that is the gap that matters,
not the display.

**Requirement 13 — "WhatsApp integration" currently means a log.** The model
records messages and the profile renders them as a thread, but every entry has
to be created by hand or by a future connector. The header button opens
`wa.me`, which is a link, not an integration. Worth being precise about this in
client conversations.

**"VIP Instant Discount" is not VIP-gated.** Not on this list, but it belongs
here: the promotion applies to any order over AED 20,000 regardless of tier.
Core loyalty has no partner-attribute condition, so gating needs a tested
override.
