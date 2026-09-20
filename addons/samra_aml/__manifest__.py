# -*- coding: utf-8 -*-
{
    'name': 'Samra AML Screening',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Sanctions and watchlist screening for customers, with a blocked till and a logged override',
    'description': """
Samra AML Screening
===================

Samra is a dealer in precious metals and stones, which in the UAE makes it a
DNFBP with customer due-diligence obligations. This module holds the part of
that obligation a system can hold: a screening status per customer, evidence
of how it was reached, and a control at the point the money moves.

It does not decide who is listed. It asks the firm's AML software and records
the answer.

The provider seam
-----------------

The screening call is configuration, not code. A provider record carries the
endpoint, the credential and a mapping from the vendor's vocabulary to this
module's -- because every vendor says "clear" differently, and the one thing
that must never be guessed is which of their words means blocked. Wiring a new
vendor is filling in a form, not editing Python.

Two provider types ship:

  * REST -- posts the customer's identifying details as JSON and reads the
    verdict back out of the response by configured paths
  * Manual -- no call at all; a compliance officer sets the status by hand.
    This exists so the control can be live before the vendor is wired, rather
    than the module waiting on procurement.

What it blocks, and what it does not
------------------------------------

A customer whose status is Blacklisted, or Possible Match, cannot be sold to:
the sale order will not confirm and the POS order will not validate. A named
compliance officer can override that with a written reason, which is recorded
against the customer and cannot be deleted by anyone.

A customer who has never been screened is NOT blocked. Screening runs on a
schedule here, so a walk-in served this morning has no status yet, and
refusing every new customer until the overnight run would stop trade rather
than control it. The till warns instead. If that is the wrong trade for the
firm's risk appetite, one flag changes it.

Screening itself runs from a cron, in batches, covering customers whose
screening has expired and those who have never been screened at all.
    """,
    'author': 'C2P Consultants FZC LLC',
    'website': 'https://www.core2plus.com',
    'license': 'LGPL-3',
    'depends': [
        'contacts',
        'sale_management',
        'point_of_sale',
    ],
    'data': [
        'security/samra_aml_groups.xml',
        'security/ir.model.access.xml',
        'data/samra_aml_data.xml',
        'views/samra_aml_provider_views.xml',
        'views/samra_aml_screening_views.xml',
        'views/samra_aml_override_views.xml',
        'wizard/samra_aml_override_wizard_views.xml',
        'views/res_partner_views.xml',
        'views/samra_aml_menus.xml',
    ],
    'installable': True,
    'application': False,
}
