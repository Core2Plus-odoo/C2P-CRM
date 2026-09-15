"""
Samra CRM - External System Integration Demo
============================================
Simulates an EXTERNAL SYSTEM (an accounting package, an e-commerce platform,
a POS terminal) talking to the Samra CRM over Odoo's standard XML-RPC API --
exactly the mechanism any real integration partner would use. Nothing here is
Samra/C2P-specific plumbing; this is the API every Odoo instance exposes out
of the box.

Run this live in front of the client to prove connectivity is real.

Configuration comes from the environment (see .env.example):

    ODOO_URL        base URL of the instance
    ODOO_DB         database name
    ODOO_LOGIN      integration user login  (do NOT use admin for a demo)
    ODOO_API_KEY    that user's API key     (required, never hard-coded)

Optional:
    ODOO_TIMEOUT        socket timeout in seconds (default 30)
    DEMO_PARTNER_EMAIL  look the demo customer up by email
    DEMO_PARTNER_ID     ...or by database id
                        (if neither is set, the first customer is used)

Usage:
    python external_integration_demo.py            # full demo, creates an order
    python external_integration_demo.py --no-write  # read-only, safe dry run
"""

import argparse
import os
import socket
import sys
import xmlrpc.client
from datetime import datetime, timezone
from urllib.parse import urlparse

# Custom fields the demo likes to show, but can live without.
OPTIONAL_PARTNER_FIELDS = ("x_vip_tier", "x_lifetime_value")

DEFAULT_TIMEOUT = 30


class DemoError(Exception):
    """A failure we can explain to the room in one line."""


# --------------------------------------------------------------------------
# Presentation helpers
# --------------------------------------------------------------------------

def narrate(msg):
    print(f"\n>>> {msg}")


def detail(msg):
    print(f"    {msg}")


# --------------------------------------------------------------------------
# Transport with a timeout, so a stalled network fails fast instead of
# hanging in front of an audience with no feedback.
# --------------------------------------------------------------------------

def _transport_for(url, timeout):
    base = xmlrpc.client.SafeTransport if urlparse(url).scheme == "https" \
        else xmlrpc.client.Transport

    class _TimeoutTransport(base):
        def make_connection(self, host):
            conn = super().make_connection(host)
            conn.timeout = timeout
            return conn

    return _TimeoutTransport()


# --------------------------------------------------------------------------
# Thin client over Odoo's XML-RPC endpoints
# --------------------------------------------------------------------------

class OdooClient:
    def __init__(self, url, db, login, api_key, timeout=DEFAULT_TIMEOUT):
        self.url = url.rstrip("/")
        self.db = db
        self.login = login
        self._api_key = api_key
        self._timeout = timeout
        self.uid = None
        self._models = None

    def connect(self):
        common = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/common",
            transport=_transport_for(self.url, self._timeout),
        )
        version = common.version()
        server_version = version.get("server_version", "unknown")

        # authenticate() returns False on bad credentials -- it does not raise,
        # so an unchecked result turns into a confusing failure several calls later.
        uid = common.authenticate(self.db, self.login, self._api_key, {})
        if not uid:
            raise DemoError(
                f"Authentication failed for user '{self.login}' on database "
                f"'{self.db}'. Check ODOO_LOGIN / ODOO_API_KEY / ODOO_DB."
            )

        self.uid = uid
        self._models = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/object",
            transport=_transport_for(self.url, self._timeout),
        )
        return server_version

    def call(self, model, method, args, kwargs=None):
        return self._models.execute_kw(
            self.db, self.uid, self._api_key, model, method, args, kwargs or {}
        )

    def search_read(self, model, domain, fields, **kwargs):
        return self.call(model, "search_read", [domain], {"fields": fields, **kwargs})

    def available_fields(self, model, candidates):
        """Which of `candidates` actually exist on `model` in this database."""
        present = self.call(model, "fields_get", [], {"attributes": ["type"]})
        return [f for f in candidates if f in present]


# --------------------------------------------------------------------------
# Value formatting -- Odoo returns False (not 0 / "") for unset fields, which
# blows up "{:,.0f}" formatting. Everything user-facing goes through these.
# --------------------------------------------------------------------------

def as_text(value, default="not set"):
    return default if value in (False, None, "") else str(value)


def as_amount(value):
    return float(value) if isinstance(value, (int, float)) and value is not False else 0.0


# --------------------------------------------------------------------------
# Demo steps
# --------------------------------------------------------------------------

def find_customer(odoo):
    """Locate a demo customer without depending on a hard-coded database id."""
    email = os.environ.get("DEMO_PARTNER_EMAIL")
    partner_id = os.environ.get("DEMO_PARTNER_ID")

    if email:
        domain, described = [["email", "=", email]], f"email {email}"
    elif partner_id:
        if not partner_id.isdigit():
            raise DemoError(f"DEMO_PARTNER_ID must be a number, got '{partner_id}'.")
        domain, described = [["id", "=", int(partner_id)]], f"id {partner_id}"
    else:
        domain, described = [["customer_rank", ">", 0]], "first customer on file"

    fields = ["name", "email", "phone"]
    fields += odoo.available_fields("res.partner", OPTIONAL_PARTNER_FIELDS)

    records = odoo.search_read("res.partner", domain, fields, limit=1, order="id")
    if not records:
        raise DemoError(
            f"No customer found ({described}). Set DEMO_PARTNER_EMAIL or "
            f"DEMO_PARTNER_ID to a record that exists in this database."
        )
    return records[0]


def show_customer(customer):
    narrate("READING a customer record (as an accounting system checking a client)...")
    detail(f"Customer: {customer['name']}")
    detail(f"Email:    {as_text(customer.get('email'))}")
    detail(f"Phone:    {as_text(customer.get('phone'))}")

    if "x_vip_tier" in customer:
        detail(f"VIP Tier: {as_text(customer['x_vip_tier'])}")
    if "x_lifetime_value" in customer:
        detail(f"Lifetime Value: AED {as_amount(customer['x_lifetime_value']):,.0f}")


def show_stock(odoo):
    """Query real quantities -- listing warehouse names proves nothing."""
    narrate("CHECKING live stock across branches (as a POS terminal would before a sale)...")

    warehouses = odoo.search_read("stock.warehouse", [], ["name", "lot_stock_id"])
    if not warehouses:
        detail("No warehouses configured in this database.")
        return

    for wh in warehouses:
        location = wh.get("lot_stock_id")
        if not location:
            detail(f"{wh['name']}: no stock location configured")
            continue

        groups = odoo.call(
            "stock.quant", "read_group",
            [[["location_id", "child_of", location[0]]], ["quantity"], []],
            {"lazy": False},
        )
        on_hand = as_amount(groups[0].get("quantity")) if groups else 0.0
        lines = groups[0].get("__count", 0) if groups else 0
        detail(f"{wh['name']}: {on_hand:,.0f} units on hand across {lines} stock entries")


def create_order(odoo, customer):
    """Create an order the way an e-commerce checkout would -- with a line on it."""
    narrate("CREATING a new order (as an e-commerce platform would on checkout)...")

    values = {
        "partner_id": customer["id"],
        # Odoo stores datetimes in UTC; datetime.now() would be off by the
        # local offset (4 hours in the UAE).
        "date_order": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }

    products = odoo.search_read(
        "product.product", [["sale_ok", "=", True]], ["name", "list_price"], limit=1
    )
    if products:
        product = products[0]
        values["order_line"] = [(0, 0, {"product_id": product["id"], "product_uom_qty": 1})]
        detail(f"Ordering 1 x {product['name']}")
    else:
        detail("No saleable product found -- creating an empty quotation instead.")

    order_id = odoo.call("sale.order", "create", [values])

    order = odoo.search_read(
        "sale.order", [["id", "=", order_id]], ["name", "amount_total", "state"]
    )[0]

    detail(f"Order created in Samra CRM: {order['name']} (id {order_id})")
    detail(f"Total: AED {as_amount(order['amount_total']):,.2f}  |  status: {order['state']}")
    detail("Visible instantly in the CRM, on any branch, to any user.")
    return order


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def load_config():
    api_key = os.environ.get("ODOO_API_KEY")
    if not api_key:
        raise DemoError(
            "ODOO_API_KEY is not set. Copy .env.example to .env, fill in the key, "
            "and export it before running (never hard-code it in this file)."
        )

    url = os.environ.get("ODOO_URL")
    db = os.environ.get("ODOO_DB")
    if not url or not db:
        raise DemoError("ODOO_URL and ODOO_DB must both be set. See .env.example.")

    timeout = os.environ.get("ODOO_TIMEOUT", str(DEFAULT_TIMEOUT))
    if not timeout.isdigit() or int(timeout) <= 0:
        raise DemoError(f"ODOO_TIMEOUT must be a positive number of seconds, got '{timeout}'.")

    return {
        "url": url,
        "db": db,
        "login": os.environ.get("ODOO_LOGIN", "integration"),
        "api_key": api_key,
        "timeout": int(timeout),
    }


def run(write_enabled):
    config = load_config()
    odoo = OdooClient(**config)

    narrate("Connecting to Samra CRM as an EXTERNAL system (e.g. an e-commerce platform)...")
    server_version = odoo.connect()
    detail(f"Connected. Odoo version: {server_version}")
    detail(f"Authenticated as '{config['login']}' (user id: {odoo.uid})")

    customer = find_customer(odoo)
    show_customer(customer)
    show_stock(odoo)

    if write_enabled:
        create_order(odoo, customer)
        narrate("DONE. An external system just read, checked stock, and wrote data --")
    else:
        narrate("Skipping order creation (--no-write).")
        narrate("DONE. An external system just read live data --")

    detail("live, in real time, using nothing but Odoo's standard API.")
    detail("This is exactly how a POS system, accounting package, or website would connect.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="read-only run: skip creating a sale order (safe against production)",
    )
    args = parser.parse_args()

    try:
        run(write_enabled=not args.no_write)
    except DemoError as exc:
        print(f"\n!!! {exc}", file=sys.stderr)
        return 1
    except xmlrpc.client.Fault as exc:
        print(f"\n!!! Odoo rejected the call: {exc.faultString.strip().splitlines()[-1]}",
              file=sys.stderr)
        return 1
    except (socket.timeout, TimeoutError):
        print(f"\n!!! Timed out talking to Odoo after {load_config()['timeout']}s.",
              file=sys.stderr)
        return 1
    except (OSError, xmlrpc.client.ProtocolError) as exc:
        print(f"\n!!! Could not reach Odoo: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
