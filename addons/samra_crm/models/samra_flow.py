# -*- coding: utf-8 -*-
"""A small branching automation engine: decide, act, end.

Adapted from a handoff that had been prototyped live via XML-RPC. Field names
and types are kept EXACTLY as the live manual models carry them, because Odoo
matches manual columns by name when a Python class adopts them -- rename one
and Odoo drops the column and recreates it, taking the flow history with it.
Everything added here is additive for that reason: new fields, never renamed
or removed ones.

THE SECURITY MODEL, WHICH IS THE PART WORTH READING

base_automation runs a rule's server action as sudo:

    actions = automation_rule.sudo().action_server_ids.with_context(...)
    for action in actions:
        res = action.run()                  # base_automation.py:996

An action step writes a field named by the step itself. Put those two
together with an ACL that let every employee edit steps, and any user could
have arbitrary fields written with superuser rights the next time anybody
created a lead. Two changes close that:

  * Authoring is a manager act. Ordinary users read flows and their logs;
    only Sales managers create or change them. (security/ir.model.access.xml)

  * A flow declares, up front, which fields its action steps may write.
    x_allowed_fields is empty by default, which refuses every set_field
    write until a manager names the fields on purpose. A manager writing
    automation is legitimately privileged; the point is that the privilege is
    now stated in the record rather than implied by the engine.

WHY FAILURES ARE NOT SWALLOWED
The prototype caught every exception into the outcome text and let the
instance finish as 'completed'. That makes the obvious health check -- are
any instances in error? -- answer no while every step is failing. A step that
raises now marks the instance 'error' and stops. The lead is still created:
the automation's own try/except sees to that, and refusing to save a customer
record because a routing rule misfired would be the worse failure.
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# A flow that reaches this many steps is looping. The prototype's guard, kept.
MAX_STEPS = 20


class SamraFlowDefinition(models.Model):
    _name = 'x_samra_flow_definition'
    _description = 'Samra Flow Definition'
    _order = 'x_name'
    _rec_name = 'x_name'

    x_name = fields.Char(string='Flow Name', required=True)
    x_target_model = fields.Char(string='Target Model (e.g. crm.lead)')
    x_trigger_type = fields.Selection(
        [('on_create', 'On Create'), ('manual', 'Manual')],
        string='Trigger', default='on_create')
    x_active = fields.Boolean(string='Active', default=True)
    x_description = fields.Text(string='Description')
    x_step_ids = fields.One2many(
        'x_samra_flow_step', 'x_flow_id', string='Steps')

    # Added, not renamed: new column, no risk to the live data.
    x_allowed_fields = fields.Char(
        string='Writable Fields',
        help="Comma-separated field names this flow's action steps may write, "
             "e.g. user_id,priority. Empty means none: a flow cannot set a "
             "field until someone names it here. Steps run with superuser "
             "rights, so this list is the boundary of what that can touch.")

    # ------------------------------------------------------------------

    def _allowed_field_set(self):
        self.ensure_one()
        raw = self.x_allowed_fields or ''
        return {name.strip() for name in raw.split(',') if name.strip()}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_for_record(self, record):
        """Execute this flow against one record. Returns the instance."""
        self.ensure_one()

        first = self.env['x_samra_flow_step'].search(
            [('x_flow_id', '=', self.id)], order='x_sequence asc', limit=1)
        if not first:
            return self.env['x_samra_flow_instance']

        Log = self.env['x_samra_flow_log']
        instance = self.env['x_samra_flow_instance'].create({
            'x_flow_id': self.id,
            'x_res_model': record._name,
            'x_res_id': record.id,
            'x_current_step_id': first.id,
            'x_status': 'running',
            'x_start_date': fields.Datetime.now(),
            'x_record_name': record.display_name,
        })

        step = first
        for _iteration in range(MAX_STEPS):
            try:
                outcome, next_step = self._execute_step(record, step)
                failed = False
            except Exception as error:  # noqa: BLE001 - recorded, then stops
                # Deliberately broad: a flow step runs configuration written by
                # a manager against live records, so anything can come back.
                # What matters is that it lands in the log AND on the instance
                # status, rather than being quietly narrated as an outcome.
                _logger.exception(
                    "Samra flow %s step %s failed on %s",
                    self.x_name, step.x_name, record)
                outcome, next_step, failed = f"ERROR: {error}", None, True

            Log.create({
                'x_instance_id': instance.id,
                'x_step_id': step.id,
                'x_timestamp': fields.Datetime.now(),
                'x_outcome': outcome,
            })

            if failed:
                instance.write({
                    'x_status': 'error',
                    'x_end_date': fields.Datetime.now(),
                })
                return instance

            if step.x_step_type == 'end' or not next_step:
                instance.write({
                    'x_status': 'completed',
                    'x_end_date': fields.Datetime.now(),
                })
                return instance

            instance.write({'x_current_step_id': next_step.id})
            step = next_step

        instance.write({
            'x_status': 'error',
            'x_end_date': fields.Datetime.now(),
        })
        Log.create({
            'x_instance_id': instance.id,
            'x_timestamp': fields.Datetime.now(),
            'x_outcome': f"ERROR: stopped after {MAX_STEPS} steps, flow loops",
        })
        return instance

    def _execute_step(self, record, step):
        """Run one step. Returns (outcome text, next step or None)."""
        if step.x_step_type == 'action':
            return self._execute_action_step(record, step)
        if step.x_step_type == 'decision':
            return self._execute_decision_step(record, step)
        if step.x_step_type == 'end':
            return 'Flow completed', None
        return f"Unknown step type {step.x_step_type!r}", None

    def _execute_action_step(self, record, step):
        self.ensure_one()

        if step.x_action_type == 'set_field':
            field_name = (step.x_action_field or '').strip()
            allowed = self._allowed_field_set()
            if not field_name:
                raise ValueError(_("Action step %s names no field.", step.x_name))
            if field_name not in allowed:
                # The whole point of the whitelist. Refusing loudly beats
                # writing a field nobody meant this flow to reach.
                raise ValueError(_(
                    "Flow %(flow)s is not allowed to write %(field)s. Add it to "
                    "the flow's Writable Fields if that is intended.",
                    flow=self.x_name, field=field_name))
            if field_name not in record._fields:
                raise ValueError(_(
                    "%(model)s has no field %(field)s.",
                    model=record._name, field=field_name))
            record.write({field_name: step.x_action_value})
            return f"Set {field_name} = {step.x_action_value}", step.x_next_step

        if step.x_action_type == 'assign_user':
            user = step.x_action_user_id
            if not user and step.x_action_value:
                # Fallback for flows configured before x_action_user_id
                # existed. Matching a person by name is fragile -- two Fatimas,
                # or one marriage, and leads route to nobody -- so it is a
                # migration path, not the supported way to configure this.
                user = self.env['res.users'].search(
                    [('name', '=', step.x_action_value)], limit=1)
            if not user:
                raise ValueError(_(
                    "Step %(step)s assigns to nobody: set a user on it.",
                    step=step.x_name))
            if 'user_id' not in record._fields:
                raise ValueError(_(
                    "%(model)s has no user_id to assign.", model=record._name))
            record.write({'user_id': user.id})
            return f"Assigned to {user.name}", step.x_next_step

        if step.x_action_type == 'create_activity':
            record.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=step.x_action_value or _('Follow up'))
            return f"Activity created: {step.x_action_value}", step.x_next_step

        raise ValueError(_("Unknown action type %s", step.x_action_type))

    def _execute_decision_step(self, record, step):
        field_name = (step.x_condition_field or '').strip()
        if field_name not in record._fields:
            raise ValueError(_(
                "%(model)s has no field %(field)s to test.",
                model=record._name, field=field_name))

        # record[name], not getattr: safe_eval blocks getattr in server-action
        # contexts, and this method is reachable from one.
        actual = record[field_name]
        expected = step.x_condition_value

        left, right = actual, expected
        try:
            left, right = float(actual), float(expected)
        except (TypeError, ValueError):
            # Not numeric on both sides, so compare as text. A Many2one would
            # otherwise compare a recordset against a string and never match.
            if hasattr(actual, '_name'):
                left = actual.display_name or ''
            left, right = str(left), str(right or '')

        operator = step.x_condition_operator
        if operator == '>':
            result = left > right
        elif operator == '<':
            result = left < right
        elif operator == '=':
            result = left == right
        elif operator == '!=':
            result = left != right
        else:
            raise ValueError(_("Unknown operator %s", operator))

        outcome = (f"{field_name} {operator} {expected} is {result} "
                   f"(actual: {actual})")
        return outcome, (step.x_next_step_if_true if result
                         else step.x_next_step_if_false)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    @api.model
    def trigger_for_model(self, record):
        """Run every active on-create flow registered for this record's model.

        Called from the automation rule's server action. One failing flow does
        not stop the others: they are independent rules that happen to share a
        trigger.
        """
        flows = self.search([
            ('x_target_model', '=', record._name),
            ('x_active', '=', True),
            ('x_trigger_type', '=', 'on_create'),
        ])
        for flow in flows:
            flow.run_for_record(record)
        return True


class SamraFlowStep(models.Model):
    _name = 'x_samra_flow_step'
    _description = 'Samra Flow Step'
    _order = 'x_sequence, id'
    _rec_name = 'x_name'

    x_flow_id = fields.Many2one('x_samra_flow_definition', string='Flow',
                                ondelete='cascade')
    x_sequence = fields.Integer(string='Sequence', default=10)
    x_name = fields.Char(string='Step Name')
    x_step_type = fields.Selection(
        [('decision', 'Decision'), ('action', 'Action'), ('end', 'End')],
        string='Step Type', default='action')

    x_condition_field = fields.Char(string='Condition Field (e.g. expected_revenue)')
    x_condition_operator = fields.Selection(
        [('>', '>'), ('<', '<'), ('=', '='), ('!=', '!=')],
        string='Operator')
    x_condition_value = fields.Char(string='Condition Value')
    x_next_step_if_true = fields.Many2one('x_samra_flow_step', string='Next Step (If True)')
    x_next_step_if_false = fields.Many2one('x_samra_flow_step', string='Next Step (If False)')

    x_action_type = fields.Selection(
        [('set_field', 'Set Field'), ('assign_user', 'Assign User'),
         ('create_activity', 'Create Activity')],
        string='Action Type')
    x_action_field = fields.Char(string='Action Field (e.g. user_id)')
    x_action_value = fields.Char(string='Action Value')
    x_next_step = fields.Many2one('x_samra_flow_step', string='Next Step')

    # Added alongside x_action_value rather than replacing it, so existing
    # name-matched steps keep working while new ones point at a real user.
    x_action_user_id = fields.Many2one('res.users', string='Assign To')


class SamraFlowInstance(models.Model):
    _name = 'x_samra_flow_instance'
    _description = 'Samra Flow Instance'
    _order = 'x_start_date desc, id desc'
    _rec_name = 'x_record_name'

    x_flow_id = fields.Many2one('x_samra_flow_definition', string='Flow')
    x_res_model = fields.Char(string='Record Model')
    x_res_id = fields.Integer(string='Record ID')
    x_current_step_id = fields.Many2one('x_samra_flow_step', string='Current Step')
    x_status = fields.Selection(
        [('running', 'Running'), ('completed', 'Completed'), ('error', 'Error')],
        string='Status', default='running')
    x_start_date = fields.Datetime(string='Started On')
    x_end_date = fields.Datetime(string='Completed On')
    x_record_name = fields.Char(string='Record Reference')

    x_log_ids = fields.One2many(
        'x_samra_flow_log', 'x_instance_id', string='Log')

    def action_open_record(self):
        """Jump to the record this ran against.

        An instance says a lead was routed; the next question is always which
        lead, and a model/id pair on screen does not answer it.
        """
        self.ensure_one()
        if not self.x_res_model or not self.x_res_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.x_res_model,
            'res_id': self.x_res_id,
            'view_mode': 'form',
        }


class SamraFlowLog(models.Model):
    _name = 'x_samra_flow_log'
    _description = 'Samra Flow Log'
    _order = 'x_timestamp desc, id desc'

    x_instance_id = fields.Many2one('x_samra_flow_instance', string='Flow Instance',
                                    ondelete='cascade')
    x_step_id = fields.Many2one('x_samra_flow_step', string='Step')
    x_timestamp = fields.Datetime(string='Timestamp')
    x_outcome = fields.Text(string='Outcome')
