# -*- coding: utf-8 -*-
"""Adopt the four flow models the same way the first three were adopted.

They were prototyped live over XML-RPC, so on the target instance they exist
as ir.model rows with state='manual' holding real flow history. Declaring them
in Python is not enough to take them over -- ir.model.create() instanciates a
manual row with _custom=True, and reflection then derives the state from that
flag rather than from the fact that a module now declares the model.

adopt_studio_models already knows how to do this; the list it works from just
grew by four. Idempotent, so an instance that never had the prototype passes
straight through.

It also rewires the automation, for a reason worth stating: post_init_hook
runs on INSTALL only. On the instance this is aimed at, samra_crm is already
installed, so the hook will not fire and the lead-create server action would
keep running the inline prototype engine it holds today -- the packaged
trigger_for_model would exist and never be called. The local upgrade proved
exactly that: every other assertion passed and the action code came back
empty. An upgrade has to do the wiring itself.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.samra_crm.hooks import _setup_flow_engine
from odoo.addons.samra_crm.models.samra_ownership import adopt_studio_models


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    adopt_studio_models(env)
    _setup_flow_engine(env)
