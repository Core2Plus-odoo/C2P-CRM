# -*- coding: utf-8 -*-
"""Refuse the upgrade if adopting the flow models would strand live data.

The four x_samra_flow_* models were prototyped over XML-RPC on the target
instance and already hold real flow history. Declaring them in Python adopts
those tables in place, which is only safe while every field name in
samra_flow.py matches the column the prototype created. Rename one and Odoo
does not migrate the data: it creates the new column empty and leaves the old
one behind with nobody reading it. Nothing errors. The flow list simply comes
up blank and the history looks deleted.

The plan was to check that by hand, by diffing a field list pasted out of the
live database against the module. This does the same comparison against the
database being upgraded, at the moment it matters, which is better than a diff
done once on one instance:

  * a declared field with no column is ordinary and expected -- that is how
    x_allowed_fields, x_action_user_id and x_log_ids arrive
  * a column no field declares is stranded prototype data. On its own it is
    not fatal (the column keeps its rows), so it is logged, not raised
  * both at once, on a table that holds rows, is the rename signature, and
    that is the one that silently loses data. Stop there.

Aborting a migration is loud and recoverable. The alternative failure is quiet
and looks like the history was deleted.
"""

import logging

from odoo import fields as odoo_fields

_logger = logging.getLogger(__name__)

# Odoo puts the log-access fields on the model class itself, so they come back
# from the class body just like a declared one, and the table has always had
# them. Comparing them either way only produces noise.
MAGIC = {'id', 'create_uid', 'create_date', 'write_uid', 'write_date'}


def _declared_columns(cls):
    """Column names the Python class expects, taken off the class itself.

    The registry has not been rebuilt yet at pre-migrate time, so cls._fields
    still describes the OLD code. The Field objects assigned in the class body
    are the new declaration, and they are what we need.
    """
    columns = set()
    for name, value in vars(cls).items():
        if not isinstance(value, odoo_fields.Field):
            continue
        if not value.store or isinstance(value, odoo_fields.One2many):
            continue
        columns.add(name)
    return columns - MAGIC


def migrate(cr, version):
    # Imported here, not at module scope: if this file cannot be imported the
    # upgrade fails with a traceback about the guard rather than the thing the
    # guard protects.
    from odoo.addons.samra_crm.models import samra_flow

    models = [
        samra_flow.SamraFlowDefinition,
        samra_flow.SamraFlowStep,
        samra_flow.SamraFlowInstance,
        samra_flow.SamraFlowLog,
    ]

    for cls in models:
        table = cls._name.replace('.', '_')

        cr.execute("SELECT to_regclass(%s)", (table,))
        if not cr.fetchone()[0]:
            # Fresh instance, or one that never ran the prototype.
            continue

        cr.execute("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = %s
        """, (table,))
        existing = {row[0] for row in cr.fetchall()} - MAGIC

        declared = _declared_columns(cls)
        missing = declared - existing
        orphaned = existing - declared

        if not orphaned:
            if missing:
                _logger.info(
                    "Samra flow: %s gains %s. Additive, nothing to migrate.",
                    table, ", ".join(sorted(missing)))
            continue

        cr.execute('SELECT COUNT(*) FROM "%s"' % table)
        rows = cr.fetchone()[0]

        if missing and rows:
            raise ValueError(
                "Refusing to upgrade samra_crm: adopting %s would strand its "
                "data.\n\n"
                "  columns present with no field declared: %s\n"
                "  fields declared with no column: %s\n"
                "  rows in the table: %d\n\n"
                "That pairing is what a renamed field looks like. Odoo will "
                "not move the data across -- it creates the new column empty "
                "and leaves the old one orphaned, and the upgrade reports "
                "success.\n\n"
                "Either rename the field in addons/samra_crm/models/"
                "samra_flow.py back to the column above, or, if the rename is "
                "deliberate, copy the data across in a migration first."
                % (table,
                   ", ".join(sorted(orphaned)),
                   ", ".join(sorted(missing)),
                   rows)
            )

        _logger.warning(
            "Samra flow: %s has %s, which no field declares. %d row(s) keep "
            "those values; nothing reads them.",
            table, ", ".join(sorted(orphaned)), rows)
