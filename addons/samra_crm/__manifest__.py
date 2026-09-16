# -*- coding: utf-8 -*-
{
    'name': 'Samra Jewellery CRM',
    'version': '19.0.1.2.0',
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
        'loyalty',
        # The flow engine creates and rewires a base.automation rule.
        'base_automation',
        # Deliberately NOT helpdesk. It is Enterprise-only, and depending on
        # it makes this module uninstallable on Community -- which is how CI
        # skipped samra_crm entirely and still reported the run as passing.
        # Nothing here needs it: _samra_tickets() already checks
        # 'helpdesk.ticket' not in self.env and returns an empty list, so the
        # profile degrades to a missing panel where Helpdesk is absent and
        # works unchanged where it is installed.
    ],
    'data': [
        'security/ir.model.access.xml',
        'data/samra_cron.xml',
        'views/res_partner_views.xml',
        'views/samra_crm_menus.xml',
        'views/samra_occasion_views.xml',
        'views/samra_transfer_views.xml',
        'views/samra_demo_data_views.xml',
        'views/samra_dashboard_views.xml',
        'views/samra_flow_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # samra_theme defines the tokens and mixins the other stylesheets
            # use. Odoo concatenates a bundle's SCSS into one compilation unit,
            # so it must be listed first -- a glob would sort scss/ last and
            # every @include would hit an undefined mixin.
            'samra_crm/static/src/scss/samra_theme.scss',
            'samra_crm/static/src/customer_360/**/*',
            'samra_crm/static/src/dashboard/**/*',
            'samra_crm/static/src/breakdown/**/*',
            'samra_crm/static/src/occasions/**/*',
        ],
        # The point of sale runs a separate frontend from its own bundle, so
        # the theme has to be listed again here -- each bundle is its own SCSS
        # compilation unit and shares nothing with the backend's.
        'point_of_sale._assets_pos': [
            'samra_crm/static/src/scss/samra_theme.scss',
            'samra_crm/static/src/pos/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'post_init_hook': 'post_init_hook',
}
