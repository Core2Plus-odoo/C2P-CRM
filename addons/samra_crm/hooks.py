# -*- coding: utf-8 -*-
"""
Post-install hook: establishes the Samra sales pipeline stages, lost reasons
and loyalty programs using get-or-create by name rather than declarative XML
records.

This is deliberate. These records may already exist on an instance where the
module is installed on top of earlier Studio-style prototyping, and a plain
<record> would create duplicates instead of adopting them.

Safe to run on:
  - A fresh Odoo instance (creates everything from scratch)
  - The already-customized Samra instance (adopts existing records by name)
"""

import logging

from .models.samra_ownership import adopt_studio_models

_logger = logging.getLogger(__name__)

# The Samra pipeline. Exactly one stage may be the winning stage.
STAGE_SPECS = [
    ('New Lead', 10),
    ('Contacted', 20),
    ('Appointment', 30),
    ('Store Visit', 40),
    ('Quotation', 50),
    ('Follow-Up', 60),
    ('Sold', 70),
]
WON_STAGE_NAME = 'Sold'

LOST_REASONS = [
    'Price',
    'Product Unavailable',
    'Customer Postponed',
    'Competitor Purchase',
    'Other',
]

# Samra Rewards: 1 point per AED 10 spent.
#
# reward_point_mode='money' grants `reward_point_amount` points per unit of
# currency, so the rate is the points-per-AED figure -- 0.1, not 10. An earlier
# version set amount=1 with minimum_amount=10, reading minimum_amount as a
# divisor; it is an order qualification threshold, and the program granted
# 1 point per AED 1 -- ten times the intended rate.
POINTS_PER_AED = 0.1

VIP_TIERS_FOR_INSTANT_DISCOUNT = ('vip', 'vvip')


def post_init_hook(env):
    # Before anything else: if Studio prototyped these models, claim them, so
    # the rest of the install and every later upgrade see a module that owns
    # what it declares.
    adopt_studio_models(env)
    _setup_pipeline(env)
    _setup_lost_reasons(env)
    _setup_loyalty_programs(env)
    _setup_flow_engine(env)


def _find_stage(env, name):
    """Find a pipeline stage by name, preferring one shared across all teams.

    Searching on name alone would adopt -- and then rewrite the sequence of --
    a stage belonging to some unrelated sales team that happens to share a
    name. Shared stages (team_id unset) are the ones this pipeline owns.
    """
    Stage = env['crm.stage']
    # crm.stage links teams through team_ids (Many2many); an empty set means the
    # stage is shared across every team, which is the one this pipeline owns.
    shared = Stage.search([('name', '=', name), ('team_ids', '=', False)], limit=1)
    return shared or Stage.search([('name', '=', name)], limit=1)


def _setup_pipeline(env):
    Stage = env['crm.stage']

    stages = env['crm.stage'].browse()
    for name, sequence in STAGE_SPECS:
        existing = _find_stage(env, name)
        if existing:
            # Realign ordering in case it drifted, but leave everything else
            # about the stage alone.
            existing.write({'sequence': sequence, 'is_won': name == WON_STAGE_NAME})
            stages |= existing
        else:
            stages |= Stage.create({
                'name': name,
                'sequence': sequence,
                'is_won': name == WON_STAGE_NAME,
            })

    # Odoo's CRM ships its own winning stage ("Won"). Left alone, the pipeline
    # ends up with two stages flagged is_won, which splits won-deal reporting
    # between them. Samra's pipeline wins at "Sold", so stand the others down.
    other_won = env['crm.stage'].search([('is_won', '=', True), ('id', 'not in', stages.ids)])
    if other_won:
        _logger.info(
            "Samra CRM: clearing is_won on %s so '%s' is the only winning stage",
            other_won.mapped('name'), WON_STAGE_NAME,
        )
        other_won.write({'is_won': False})


def _setup_lost_reasons(env):
    LostReason = env['crm.lost.reason']
    for name in LOST_REASONS:
        if not LostReason.search([('name', '=', name)], limit=1):
            LostReason.create({'name': name})


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
                'reward_point_amount': POINTS_PER_AED,
                'reward_point_mode': 'money',
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
    else:
        _logger.info(
            "Samra CRM: 'Samra Rewards' already exists; leaving its earning rate alone. "
            "If it was created with the 1-point-per-AED rate, correct it manually -- "
            "already-issued balances are a commercial decision, not a migration."
        )

    if not Program.search([('name', '=', 'VIP Instant Discount')], limit=1):
        Program.create({
            'name': 'VIP Instant Discount',
            'program_type': 'promotion',
            'trigger': 'auto',
            'applies_on': 'current',
            'portal_visible': False,
            'rule_ids': [(0, 0, {
                'minimum_amount': 20000,
                'reward_point_amount': 1,
                'reward_point_mode': 'order',
            })],
            'reward_ids': [
                (0, 0, {'reward_type': 'discount', 'discount': 7, 'discount_mode': 'percent',
                        'discount_applicability': 'order', 'required_points': 1}),
            ],
        })


# ----------------------------------------------------------------------
# Flow engine
# ----------------------------------------------------------------------

FLOW_ACTION_NAME = 'Samra Flow Engine - Execute On Lead Create'
FLOW_AUTOMATION_NAME = 'Samra Flow Engine Trigger - Lead Create'

# One line, calling a method that lives in this repo. The live instance
# currently holds the whole engine inline in the server action's code, which
# means the logic routing real leads is in a database column nobody reviews
# and nothing tests. Rewriting it to a call is the point of packaging this.
FLOW_ENGINE_CODE = "env['x_samra_flow_definition'].trigger_for_model(record)"


def _setup_flow_engine(env):
    """Point the lead-create automation at the packaged engine.

    Get-or-create by name: this installs onto an instance where the automation
    and its action already exist, prototyped over XML-RPC, and creating a
    second one would run every flow twice.
    """
    # Declared in depends, so this should always hold. Checked anyway: this
    # runs from a migration, and an exception there fails the whole registry
    # load rather than one feature -- which is how an instance ends up serving
    # a bare 500 on every URL instead of a CRM with one dead menu.
    if 'base.automation' not in env:
        _logger.warning(
            "Samra CRM: base_automation is absent, flow engine left unwired")
        return

    lead_model = env['ir.model'].search([('model', '=', 'crm.lead')], limit=1)
    if not lead_model:
        _logger.info("Samra CRM: crm.lead not installed, skipping flow engine")
        return

    action = env['ir.actions.server'].search(
        [('name', '=', FLOW_ACTION_NAME)], limit=1)
    if action:
        action.write({'code': FLOW_ENGINE_CODE, 'model_id': lead_model.id})
    else:
        action = env['ir.actions.server'].create({
            'name': FLOW_ACTION_NAME,
            'model_id': lead_model.id,
            'state': 'code',
            'code': FLOW_ENGINE_CODE,
        })

    automation = env['base.automation'].search(
        [('name', '=', FLOW_AUTOMATION_NAME)], limit=1)
    values = {'action_server_ids': [(6, 0, [action.id])]}
    if automation:
        automation.write(values)
    else:
        env['base.automation'].create(dict(
            values,
            name=FLOW_AUTOMATION_NAME,
            model_id=lead_model.id,
            trigger='on_create',
        ))

    _logger.info("Samra CRM: flow engine wired to %s", FLOW_ACTION_NAME)
