# -*- coding: utf-8 -*-
"""
Post-install hook: safely establishes the Samra sales pipeline stages and
lost reasons using get-or-create by name, rather than declarative XML data
records. This is deliberate — see the note in data/crm_lost_reason_data.xml
placeholder removal: these records may already exist on an instance where
this module is being installed on top of earlier Studio-style prototyping,
and a plain <record> would create duplicates instead of adopting them.

Safe to run on:
  - A fresh Odoo instance (creates everything from scratch)
  - The already-customized Samra instance (finds existing records by name,
    only touches sequence/is_won if missing, creates nothing extra)
"""


def post_init_hook(env):
    Stage = env['crm.stage']
    stage_specs = [
        ('New Lead', 10, False),
        ('Contacted', 20, False),
        ('Appointment', 30, False),
        ('Store Visit', 40, False),
        ('Quotation', 50, False),
        ('Follow-Up', 60, False),
        ('Sold', 70, True),
    ]
    for name, sequence, is_won in stage_specs:
        existing = Stage.search([('name', '=', name)], limit=1)
        if existing:
            # Make sure sequence/is_won reflect the intended pipeline order,
            # in case they drifted, but don't touch anything else about it.
            existing.write({'sequence': sequence, 'is_won': is_won})
        else:
            Stage.create({'name': name, 'sequence': sequence, 'is_won': is_won})

    LostReason = env['crm.lost.reason']
    for name in ['Price', 'Product Unavailable', 'Customer Postponed', 'Competitor Purchase', 'Other']:
        if not LostReason.search([('name', '=', name)], limit=1):
            LostReason.create({'name': name})

    _setup_loyalty_programs(env)


def _setup_loyalty_programs(env):
    Program = env['loyalty.program']

    if not Program.search([('name', '=', 'Samra Rewards')], limit=1):
        Program.create({
            'name': 'Samra Rewards',
            'program_type': 'loyalty',
            'trigger': 'auto',
            'applies_on': 'both',
            'portal_visible': True,
            'rule_ids': [(0, 0, {
                'reward_point_amount': 1,
                'reward_point_mode': 'money',
                'minimum_amount': 10,  # 1 point per AED 10 spent
                'reward_point_name': 'Points',
            })],
            'reward_ids': [
                (0, 0, {'reward_type': 'discount', 'discount': 5, 'discount_mode': 'percent',
                        'discount_applicability': 'order', 'required_points': 100}),
                (0, 0, {'reward_type': 'discount', 'discount': 10, 'discount_mode': 'percent',
                        'discount_applicability': 'order', 'required_points': 250}),
                (0, 0, {'reward_type': 'discount', 'discount': 15, 'discount_mode': 'percent',
                        'discount_applicability': 'order', 'required_points': 500}),
            ],
        })

    if not Program.search([('name', '=', 'VIP Instant Discount')], limit=1):
        Program.create({
            'name': 'VIP Instant Discount',
            'program_type': 'promotion',
            'trigger': 'auto',
            'applies_on': 'current',
            'portal_visible': False,
            'rule_ids': [(0, 0, {
                'minimum_amount': 20000,  # proxy threshold for high-value/VIP-level orders
                'reward_point_amount': 1,
                'reward_point_mode': 'order',
            })],
            'reward_ids': [
                (0, 0, {'reward_type': 'discount', 'discount': 7, 'discount_mode': 'percent',
                        'discount_applicability': 'order', 'required_points': 1}),
            ],
        })
