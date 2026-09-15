# -*- coding: utf-8 -*-
"""Adopt the Studio-created models on an already-installed database.

post_init_hook only runs on a fresh install, so it cannot reach the instance
where this module is already installed and the three models still read
state='manual', modules=''. That is what an upgrade script is for.

Odoo checks the signature and requires (cr, installed_version) exactly --
see odoo/modules/migration.py, which raises a TypeError otherwise.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.samra_crm.models.samra_ownership import adopt_studio_models


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    adopt_studio_models(env)
