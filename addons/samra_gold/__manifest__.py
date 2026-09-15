# -*- coding: utf-8 -*-
{
    'name': 'Samra Gold Rate & Weight Pricing',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Daily gold rate, purity and weight-based pricing for jewellery',
    'description': """
Samra Gold Rate & Weight Pricing
=================================

A jewellery price is not a number somebody types in. It is arithmetic over a
rate that moves every morning:

    metal   = net weight x rate for its karat x (1 + wastage)
    price   = metal + making charge + stone value

Standard Odoo pricelists cannot express that -- they discount a price, they do
not compute one from a commodity rate. This module supplies the rate, the
purity arithmetic and the making-charge policy, then writes the result into
the product's ordinary sales price.

That last part is deliberate. Once list_price is correct for today, every
other part of Odoo works unchanged: quotations, the POS, pricelists,
promotions, margin reporting. The alternative -- intercepting price at each
point of sale -- means fighting the POS, which runs its own trimmed frontend
and would need the rate table shipped to every till.

Rates are shared across companies. A gold rate is a fact about the market, not
about a branch, so the records carry no company_id and all four companies read
the same morning figure. Making-charge policy is per company, because that is
a commercial decision each one makes for itself.
    """,
    'author': 'C2P Consultants FZC LLC',
    'website': 'https://www.core2plus.com',
    'license': 'LGPL-3',
    'depends': [
        'product',
        'sale',
    ],
    'data': [
        'security/ir.model.access.xml',
        'views/samra_gold_rate_views.xml',
        'views/product_views.xml',
    ],
    'installable': True,
    'application': False,
}
