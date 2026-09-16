# -*- coding: utf-8 -*-
"""Take ownership of models Studio created before this module existed.

The three custom models were prototyped in Studio, which created their
ir.model rows with state='manual'. When the packaged module later declared the
same _name in Python, it did not take them over, and on this database they
still read state='manual', modules=''.

The mechanism, from odoo/addons/base/models/ir_model.py:

  * ir.model.create() instanciates every row whose state is 'manual', and that
    generated class carries _custom = True.
  * _reflect_model_params() derives the row's state from that flag:
    'manual' if model._custom else 'base'. A Python class declaring the same
    model cannot win, because the manual class is merged into the same
    registry entry and its _custom survives.
  * _reflect_models() only writes an XML id when model._module == module.
    A model Odoo considers custom is not attributed to the addon, so no
    samra_crm.model_x_samra_wishlist is ever created.

That last point is why the access rules had to resolve model_id by search
rather than by XML id. The workaround was right; this is the cause.

Consequences of leaving it: the models belong to no module, so an upgrade
never revisits them, state keeps contradicting where the code actually lives,
and anything keyed on module ownership -- XML ids, uninstall, Studio export --
behaves inconsistently.

The repair has to go around the ORM. ir.model.write() explicitly refuses to
change state:

    for unmodifiable_field in ('model', 'state', 'abstract', 'transient'):
        if unmodifiable_field in vals and ...:
            raise UserError(...)

which is a sensible guard against doing this by accident, and exactly the kind
of thing a migration exists to do on purpose. Once the row reads 'base' it is
no longer in the manual set, so the next registry load stops generating the
_custom class, reflection agrees, and the XML id appears on its own. One run
and it self-heals.

NOTE ON BLAST RADIUS: after this, samra_crm owns these models. Uninstalling it
will drop their tables and the data in them, which it would not have done
before. That is what ownership means and it is the correct end state, but it
is a real change and worth knowing before anyone uninstalls to "clean up".
"""

import logging

_logger = logging.getLogger(__name__)

MODULE = 'samra_crm'

# Models this module declares in Python that Studio may have created first.
STUDIO_MODELS = (
    'x_samra_wishlist',
    'x_samra_viewed_product',
    'x_samra_whatsapp_log',
    # Prototyped live over XML-RPC before the flow engine was packaged, so
    # they arrive here the same way the first three did: manual rows holding
    # real data that this module now declares in Python.
    'x_samra_flow_definition',
    'x_samra_flow_step',
    'x_samra_flow_instance',
    'x_samra_flow_log',
)


def _xmlid_model(model_name):
    return f"{MODULE}.model_{model_name.replace('.', '_')}"


def _xmlid_field(model_name, field_name):
    return f"{MODULE}.field_{model_name.replace('.', '_')}__{field_name}"


def adopt_studio_models(env):
    """Flip Studio-created models and their declared fields to module ownership.

    Idempotent: rows already reading 'base' are skipped, and _update_xmlids is
    an upsert.
    """
    adopted_models, adopted_fields = [], 0

    for model_name in STUDIO_MODELS:
        record = env['ir.model'].sudo().search([('model', '=', model_name)], limit=1)
        if not record:
            _logger.info("Samra CRM: %s not present, nothing to adopt", model_name)
            continue

        if record.state != 'base':
            env.cr.execute(
                "UPDATE ir_model SET state = 'base' WHERE id = %s", (record.id,))
            adopted_models.append(model_name)

        env['ir.model.data'].sudo()._update_xmlids([{
            'xml_id': _xmlid_model(model_name),
            'record': record,
        }])

        adopted_fields += _adopt_fields(env, model_name)

    if adopted_models or adopted_fields:
        # The rows changed underneath the ORM, so drop what it has cached.
        env.invalidate_all()
        _logger.info(
            "Samra CRM: adopted %s model(s) %s and %s field(s) from Studio",
            len(adopted_models), adopted_models, adopted_fields)
    else:
        _logger.info("Samra CRM: model ownership already correct")

    return adopted_models, adopted_fields


def _adopt_fields(env, model_name):
    """Adopt only the fields this module actually declares.

    Deliberately narrow. Claiming a field means uninstalling samra_crm drops
    it, so a column somebody added in Studio that this module knows nothing
    about must stay unowned -- otherwise an uninstall would take their data
    with it.
    """
    if model_name not in env:
        return 0

    declared = set(env[model_name]._fields)
    fields = env['ir.model.fields'].sudo().search([
        ('model', '=', model_name),
        ('name', 'in', list(declared)),
    ])
    if not fields:
        return 0

    stale = fields.filtered(lambda f: f.state != 'base')
    if stale:
        env.cr.execute(
            "UPDATE ir_model_fields SET state = 'base' WHERE id IN %s",
            (tuple(stale.ids),))

    env['ir.model.data'].sudo()._update_xmlids([{
        'xml_id': _xmlid_field(model_name, field.name),
        'record': field,
    } for field in fields])

    return len(stale)


# --- Adoption has to happen before the registry is set up -------------------
#
# Doing this in post-migrate was wrong, and production found it in the one way
# CI could not: on a database where these models are manual, the registry
# builds them from ir_model_fields, not from the Python class. A field the
# class declares and the prototype never had -- x_allowed_fields -- therefore
# does not exist when Odoo validates the views, and the upgrade dies with
#
#     Field "x_allowed_fields" does not exist in model "x_samra_flow_definition"
#
# before post-migrate ever runs. The ordering only matters when an adoption
# ALSO adds a field, which is why the first three models adopted cleanly.
#
# So the state flip moves to pre-migrate, which runs before setup_models().
# It is raw SQL on purpose: at that point in the load the ORM cannot be
# trusted to have these models set up at all, and ir.model.write() refuses to
# change state anyway.

def _declared_fields_by_model():
    """Field names each STUDIO_MODELS class declares, read off the classes.

    The registry is mid-build when this is needed, so model._fields is not
    available or still describes the old code. The Field objects in the class
    bodies are the new declaration.
    """
    import importlib
    import pkgutil

    from odoo import fields as odoo_fields
    from odoo.addons.samra_crm import models as models_package

    declared = {}
    for info in pkgutil.iter_modules(models_package.__path__):
        module = importlib.import_module(f"{models_package.__name__}.{info.name}")
        for obj in vars(module).values():
            if not isinstance(obj, type):
                continue
            model_name = getattr(obj, '_name', None)
            if model_name not in STUDIO_MODELS:
                continue
            declared.setdefault(model_name, set()).update(
                name for name, value in vars(obj).items()
                if isinstance(value, odoo_fields.Field)
            )
    return declared


def claim_models_before_setup(cr):
    """Flip the manual rows to 'base' so the Python classes govern the setup.

    Only fields this module declares are claimed -- a column somebody added in
    Studio stays manual, for the same reason _adopt_fields is narrow: claiming
    it would mean an uninstall deletes their data.

    Idempotent, and a no-op on a database that never had the prototype.
    """
    cr.execute(
        "UPDATE ir_model SET state = 'base' "
        " WHERE model IN %s AND state != 'base' RETURNING model",
        (tuple(STUDIO_MODELS),))
    claimed = [row[0] for row in cr.fetchall()]

    fields_claimed = 0
    for model_name, names in _declared_fields_by_model().items():
        if not names:
            continue
        cr.execute(
            "UPDATE ir_model_fields SET state = 'base' "
            " WHERE model = %s AND name IN %s AND state != 'base'",
            (model_name, tuple(names)))
        fields_claimed += cr.rowcount

    if claimed or fields_claimed:
        _logger.info(
            "Samra CRM: claimed %s before setup, and %s field(s)",
            claimed or "no models", fields_claimed)
    return claimed, fields_claimed
