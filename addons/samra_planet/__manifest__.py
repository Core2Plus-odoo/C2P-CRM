# -*- coding: utf-8 -*-
{
    'name': 'Samra Planet Tax-Free',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Tourist tax-free VAT refund issuance via Planet Payment',
    'description': """
Samra Planet Tax-Free
======================

A tourist buying at Samra is entitled to reclaim VAT on departure, and that
reclaim is issued through Planet Payment, not through Odoo. This module's job
is narrow: mark a customer as a tourist, capture the passport a refund is
filed against, and record what Planet issued back -- a tag number and a QR
code that goes on the receipt.

Same provider seam as samra_aml, on purpose
--------------------------------------------

Nobody at Samra has yet shared Planet's real API documentation -- it is
action item #3 in the transformation MoM's own tracker, still "in progress".
Building against the MoM's sample payload as though it were the real contract
would repeat the mistake the flow engine made with a field list nobody had
verified. So the provider is configuration -- endpoint, credential, and a
mapping from Planet's response fields onto this module's -- exactly as
samra_aml's is, and for the same reason: whichever shape the real API turns
out to have, wiring it is filling in a form, not rewriting the module.

It ships with a manual provider active by default, so a tax-free tag can be
recorded by hand today and the integration can be switched on later without
anyone's workflow changing underneath them.

What happens on confirmation
-----------------------------

A sale order confirmed for a customer flagged as a tourist automatically
requests a tag from the active provider. Unlike AML, a failure here never
blocks the sale -- a tourist not getting their tax-free tag immediately is an
inconvenience to be corrected, not a reason to refuse a paying customer at the
counter. The same happens at the POS, on order validation.
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
        'security/samra_planet_groups.xml',
        'security/ir.model.access.xml',
        'data/samra_planet_data.xml',
        'views/samra_planet_provider_views.xml',
        'views/samra_planet_issuance_views.xml',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'views/samra_planet_menus.xml',
    ],
    'installable': True,
    'application': False,
}
