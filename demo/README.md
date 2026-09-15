# External Integration Demo

`external_integration_demo.py` proves — live, against a real Odoo instance —
that an external system can read from and write to the Samra CRM over Odoo's
standard XML-RPC API. It is the same mechanism a POS terminal, accounting
package or e-commerce platform would use; there is no Samra-specific plumbing
involved.

## Setup

```bash
cp .env.example .env     # then fill in ODOO_API_KEY
set -a && source .env && set +a
python3 demo/external_integration_demo.py
```

No third-party dependencies — `xmlrpc.client` is in the standard library.
Python 3.9+.

## Running it

| Command | Effect |
| --- | --- |
| `python3 demo/external_integration_demo.py` | Full demo: reads a customer, queries live stock, creates a sale order |
| `python3 demo/external_integration_demo.py --no-write` | Read-only. Safe to point at production |

The full run **creates a real sale order** in whichever database you point it
at. Use `--no-write` to rehearse, or point `ODOO_DB` at a staging copy.

## Before demoing

- Use a dedicated integration user, not `admin`. It makes the demo more
  persuasive, not less — you can answer "what can a partner actually touch?"
  by pointing at the access group.
- Do a `--no-write` dry run against the same database you'll demo against.
  Custom fields and warehouse setups differ between instances.
- Clean up accumulated draft quotations afterwards if you demoed against
  production.

## Configuration

All configuration comes from the environment; nothing is hard-coded.

| Variable | Required | Purpose |
| --- | --- | --- |
| `ODOO_URL` | yes | Instance base URL |
| `ODOO_DB` | yes | Database name |
| `ODOO_LOGIN` | no (default `integration`) | Integration user login |
| `ODOO_API_KEY` | yes | That user's API key |
| `ODOO_TIMEOUT` | no (default `30`) | Socket timeout, seconds |
| `DEMO_PARTNER_EMAIL` | no | Look the demo customer up by email |
| `DEMO_PARTNER_ID` | no | ...or by database id |

If neither `DEMO_PARTNER_*` is set the script uses the first customer on file,
so it works against a fresh database without edits.

## How it degrades

The script is built to fail in readable sentences rather than tracebacks,
because it runs in front of clients:

- Bad credentials are caught at authentication, not three calls later
  (`authenticate` returns `False` rather than raising).
- The custom fields `x_vip_tier` and `x_lifetime_value` are probed with
  `fields_get` and skipped if the database doesn't have them.
- Unset Odoo fields come back as `False`, not `0` or `""` — every displayed
  value is coerced before formatting.
- A missing customer, an absent warehouse location and a database with no
  saleable products each produce a one-line explanation and keep going where
  they can.
- Every call carries a socket timeout, so a stalled network fails fast instead
  of hanging silently.
