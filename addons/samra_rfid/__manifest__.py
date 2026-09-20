# -*- coding: utf-8 -*-
{
    'name': 'Samra RFID Stock Sync',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Nightly stock push to a third-party RFID system, and the morning gap analysis',
    'description': """
Samra RFID Stock Sync
=======================

Every piece in a Samra boutique carries an RFID tag, and the mall's overnight
scan is the only count anybody trusts by morning. This module's job is the
Odoo side of that reconciliation: push what the book says is on hand, and
record what the RFID scan actually found, so the gap between the two is a
number on a screen rather than a manual recount.

Same provider seam as samra_aml and samra_planet, for the same reason
-----------------------------------------------------------------------

Nobody has yet shared the RFID vendor's hardware or API specification -- it
is action item #4 in the transformation MoM's own tracker, still open. So,
again, the provider is configuration: an endpoint and a credential, not a
hard-coded shape. It ships with a manual provider active by default, which
does not call out anywhere -- it exists so the nightly job, the comparison
model and the gap report all work today, with a random small variance
standing in for a real scan, and switching to the vendor's real endpoint
later changes nothing else.

What runs each morning
------------------------

A scheduled job reads on-hand quantity by product and location, pushes the
snapshot to the active provider, and records what came back against each
line as the RFID-reported count. A push with no discrepancies is not worth
opening; the list is sorted and highlighted so the lines that need a look are
the only ones anyone has to read.
    """,
    'author': 'C2P Consultants FZC LLC',
    'website': 'https://www.core2plus.com',
    'license': 'LGPL-3',
    'depends': [
        'stock',
    ],
    'data': [
        'security/samra_rfid_groups.xml',
        'security/ir.model.access.xml',
        'data/samra_rfid_data.xml',
        'views/samra_rfid_provider_views.xml',
        'views/samra_rfid_push_views.xml',
        'views/samra_rfid_menus.xml',
    ],
    'installable': True,
    'application': False,
}
