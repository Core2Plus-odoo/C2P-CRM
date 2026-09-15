# Samra CRM — External Integration API

REST endpoints for POS terminals, accounting packages, storefronts and any
other system that needs to read or write Samra CRM data without knowing Odoo's
internal model and field names.

Base path: `/api/samra`

## Authentication

Every request carries an Odoo API key in the `X-API-Key` header.

```
X-API-Key: 7f3c9a...
```

Keys are issued through standard Odoo UI — **Settings → Users → _user_ →
Account Security → New API Key** — and are validated against Odoo's own key
store at the `rpc` scope. A key created for XML-RPC works here unchanged.

This matters operationally: keys are revoked in the same place they are
issued, and a request executes with exactly that user's access rights. Issue
each integration its own user with a restricted access group. An endpoint
cannot read anything the key's user could not read through the UI.

Missing header or unknown/revoked key → `401`.

## Conventions

- Request and response bodies are plain JSON (`application/json`).
- Status codes are conventional: `200` read, `201` created, `400` malformed
  request, `401` auth failure, `404` unknown record, `500` server fault.
- Errors are shaped `{"error": {"code": 404, "message": "..."}}`.
- Monetary values are numbers in the company currency (AED); the currency code
  is returned alongside where a figure could be ambiguous.
- This is **not** Odoo's JSON-RPC envelope. A failure is a non-2xx status, not
  a `200` with an error inside it.

---

## `GET /api/samra/customers/<id>`

Customer profile plus a purchase-history summary.

```bash
curl -H "X-API-Key: $SAMRA_API_KEY" \
     https://samra.example.com/api/samra/customers/17
```

```json
{
  "id": 17,
  "name": "Mona Al Habtoor",
  "email": "mona@example.com",
  "phone": "+971 4 000 0000",
  "mobile": "+971 50 000 0000",
  "city": "Dubai",
  "nationality": "United Arab Emirates",
  "vip_tier": "vvip",
  "salesperson": "Aisha Khan",
  "tags": ["Bridal", "High Value"],
  "consent": { "whatsapp": true, "sms": false },
  "preferences": {
    "gold_colour": "Yellow Gold",
    "category": "Necklaces",
    "collection": "Heritage",
    "size": "16in",
    "diamond_spec": "VS1 F",
    "gemstone": "Emerald",
    "style": "Classic",
    "budget": 75000.0
  },
  "purchase_summary": {
    "lifetime_value": 412000.0,
    "purchase_frequency": 9,
    "last_purchase_date": "2026-08-02",
    "days_since_purchase": 44,
    "at_risk": false
  },
  "recent_orders": [
    {
      "id": 241,
      "name": "S00241",
      "invoices": ["INV/2026/0117"],
      "date": "2026-08-02",
      "amount_total": 58000.0,
      "state": "sale",
      "branch": "Mall of the Emirates",
      "salesperson": "Aisha Khan",
      "lines": [
        {
          "product_id": 88,
          "sku": "NCK-YG-22-EM",
          "description": "Heritage Necklace (Yellow Gold, 22K, Emerald)",
          "qty": 1.0,
          "price": 58000.0,
          "subtotal": 58000.0,
          "gold_weight": 42.5,
          "stone_details": "1.20ct emerald, oval"
        }
      ]
    }
  ],
  "currency": "AED"
}
```

`recent_orders` is capped at the 10 most recent confirmed orders. Drafts and
cancellations are excluded.

---

## `GET /api/samra/stock/<product_id>`

Live availability of one product across every branch.

```bash
curl -H "X-API-Key: $SAMRA_API_KEY" \
     https://samra.example.com/api/samra/stock/88
```

```json
{
  "product_id": 88,
  "sku": "NCK-YG-22-EM",
  "name": "Heritage Necklace (Yellow Gold, 22K, Emerald)",
  "list_price": 58000.0,
  "gold_weight": 42.5,
  "stone_details": "1.20ct emerald, oval",
  "total_on_hand": 4.0,
  "branches": [
    {
      "warehouse_id": 1,
      "branch": "Mall of the Emirates",
      "quantity_on_hand": 2.0,
      "quantity_reserved": 1.0,
      "quantity_available": 1.0
    },
    {
      "warehouse_id": 2,
      "branch": "Dubai Hills Mall",
      "quantity_on_hand": 2.0,
      "quantity_reserved": 0.0,
      "quantity_available": 2.0
    }
  ]
}
```

Use `quantity_available` (on hand minus reserved) to decide whether you can
sell the item — `quantity_on_hand` includes stock already promised elsewhere.

---

## `POST /api/samra/orders`

Create an order, as a checkout or POS sale would.

```bash
curl -X POST \
     -H "X-API-Key: $SAMRA_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
           "partner_id": 17,
           "warehouse_id": 1,
           "client_order_ref": "WEB-10024",
           "confirm": true,
           "lines": [
             { "product_id": 88, "quantity": 1 },
             { "product_id": 91, "quantity": 2, "price_unit": 4200.0 }
           ]
         }' \
     https://samra.example.com/api/samra/orders
```

| Field | Required | Notes |
| --- | --- | --- |
| `partner_id` | yes | Existing customer id |
| `lines` | yes | Non-empty array of `{product_id, quantity}` |
| `lines[].price_unit` | no | Overrides Odoo pricing — for an externally-discounted line |
| `warehouse_id` | no | Branch fulfilling the order; company default otherwise |
| `client_order_ref` | no | Your reference, for reconciliation |
| `confirm` | no | `true` confirms immediately; otherwise it stays a quotation |

```json
{
  "id": 318,
  "name": "S00318",
  "state": "sale",
  "partner_id": 17,
  "amount_untaxed": 66400.0,
  "amount_tax": 3320.0,
  "amount_total": 69720.0,
  "currency": "AED"
}
```

Returns `201`. Totals are computed by Odoo including VAT, so treat them as
authoritative over anything your system calculated.

---

## `GET /api/samra/loyalty/<partner_id>`

Points balance and which rewards that balance can buy.

```bash
curl -H "X-API-Key: $SAMRA_API_KEY" \
     https://samra.example.com/api/samra/loyalty/17
```

```json
{
  "partner_id": 17,
  "name": "Mona Al Habtoor",
  "vip_tier": "vvip",
  "points_balance": 4120.0,
  "rewards": [
    { "id": 1, "description": "5% discount on your order",  "required_points": 100, "affordable": true },
    { "id": 2, "description": "10% discount on your order", "required_points": 250, "affordable": true },
    { "id": 3, "description": "15% discount on your order", "required_points": 500, "affordable": true }
  ]
}
```

`affordable` is computed against the current balance, so a POS can show
redeemable rewards without re-implementing the threshold logic.

---

## Error responses

```json
{ "error": { "code": 404, "message": "No customer with id 9999." } }
```

| Status | Meaning |
| --- | --- |
| `400` | Malformed body, missing required field, empty `lines` |
| `401` | Missing `X-API-Key`, or the key is unknown or revoked |
| `404` | Referenced customer, product or warehouse does not exist |
| `500` | Server fault. Details are logged server-side, never returned |

## Not yet implemented

- No rate limiting. Put it at the reverse proxy until there is a reason to
  build it into the module.
- No pagination on `recent_orders`; it is a fixed 10. Use XML-RPC against
  `sale.order` for full history.
- No webhooks. Integrations poll; the module does not call out.
- Returns, exchanges and refunds are not exposed. `POST /orders` creates
  forward sales only.
