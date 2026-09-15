# -*- coding: utf-8 -*-
{
    'name': 'Samra Jewellery CRM',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Custom CRM extensions for Samra Jewellery — clienteling, WhatsApp log, loyalty & discounts',
    'description': """
Samra Jewellery CRM
====================
Custom CRM extensions built for Samra Jewellery on top of standard Odoo CRM, Sales,
Point of Sale, Inventory, Helpdesk, and Loyalty & Referral apps.

This module formalizes customizations originally prototyped via Studio into a proper,
version-controlled, upgrade-safe module:

- Customer 360° fields on Contacts (VIP tier, jewellery preferences, consent, lifetime value)
- Wishlist tracking
- Viewed product logging
- WhatsApp message log (mock/demo integration point — ready for a real WhatsApp
  Business API connector to be wired in)
- Samra Rewards & VIP Instant Discount loyalty/discount programs (data-loaded)

Field and model names intentionally match the original Studio-prototyped names
(x_vip_tier, x_samra_wishlist, etc.) so this module can be installed over an
instance where those were created via Studio, without losing existing data —
Odoo's ORM will adopt the existing columns rather than recreating them, provided
field types match exactly.
    """,
    'author': 'C2P Consultants FZC LLC',
    'website': 'https://www.core2plus.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'contacts',
        'crm',
        'sale_management',
        'stock',
        'point_of_sale',
        'helpdesk',
        'loyalty',
    ],
    'data': [
        'security/ir.model.access.xml',
        'data/samra_cron.xml',
        'views/res_partner_views.xml',
        'views/samra_crm_menus.xml',
        'views/samra_transfer_views.xml',
        'views/samra_dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'samra_crm/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'post_init_hook': 'post_init_hook',
}
