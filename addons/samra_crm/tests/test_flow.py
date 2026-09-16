# -*- coding: utf-8 -*-
"""The flow engine, and mostly the boundary around it.

The engine's steps run with superuser rights, because base_automation runs a
rule's server action as sudo. Most of what follows asserts that the whitelist
holding that in check actually holds -- a routing rule that quietly gains the
ability to write any field is the failure worth a permanent test.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSamraFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Flow = cls.env['x_samra_flow_definition']
        cls.Step = cls.env['x_samra_flow_step']
        cls.Instance = cls.env['x_samra_flow_instance']
        cls.Lead = cls.env['crm.lead']
        cls.senior = cls.env['res.users'].search([('share', '=', False)], limit=1)

        # Other flows on the database would also fire on create and muddy the
        # assertions below, so this suite owns the field.
        cls.Flow.search([]).write({'x_active': False})

        cls.flow = cls.Flow.create({
            'x_name': 'Test High-Value Routing',
            'x_target_model': 'crm.lead',
            'x_trigger_type': 'on_create',
            'x_active': True,
            'x_allowed_fields': 'priority',
        })
        cls.decide = cls.Step.create({
            'x_flow_id': cls.flow.id, 'x_sequence': 10, 'x_name': 'Over 20k?',
            'x_step_type': 'decision', 'x_condition_field': 'expected_revenue',
            'x_condition_operator': '>', 'x_condition_value': '20000'})
        cls.assign = cls.Step.create({
            'x_flow_id': cls.flow.id, 'x_sequence': 20, 'x_name': 'Assign',
            'x_step_type': 'action', 'x_action_type': 'assign_user',
            'x_action_user_id': cls.senior.id})
        cls.pool = cls.Step.create({
            'x_flow_id': cls.flow.id, 'x_sequence': 30, 'x_name': 'Pool',
            'x_step_type': 'action', 'x_action_type': 'set_field',
            'x_action_field': 'priority', 'x_action_value': '0'})
        cls.end = cls.Step.create({
            'x_flow_id': cls.flow.id, 'x_sequence': 40, 'x_name': 'End',
            'x_step_type': 'end'})
        cls.decide.write({'x_next_step_if_true': cls.assign.id,
                          'x_next_step_if_false': cls.pool.id})
        cls.assign.x_next_step = cls.end.id
        cls.pool.x_next_step = cls.end.id

    def _run_for(self, lead):
        return self.Instance.search(
            [('x_res_model', '=', 'crm.lead'), ('x_res_id', '=', lead.id)],
            limit=1)

    # -- the path that actually matters ---------------------------------

    def test_automation_routes_a_high_value_lead(self):
        """Created through the ORM, routed by base_automation, not by us.

        An earlier version of this suite called the engine directly and would
        have passed while the automation was wired to nothing.
        """
        lead = self.Lead.create({'name': 'Bridal set', 'type': 'opportunity',
                                 'expected_revenue': 75000})
        lead.invalidate_recordset()
        run = self._run_for(lead)
        self.assertTrue(run, "automation did not fire on create")
        self.assertEqual(run.x_status, 'completed')
        self.assertEqual(lead.user_id, self.senior)

    def test_automation_leaves_a_small_lead_alone(self):
        lead = self.Lead.create({'name': 'Repair quote', 'type': 'opportunity',
                                 'expected_revenue': 300, 'user_id': False})
        lead.invalidate_recordset()
        self.assertEqual(self._run_for(lead).x_status, 'completed')
        self.assertFalse(lead.user_id)
        self.assertEqual(lead.priority, '0')

    def test_every_step_is_logged(self):
        lead = self.Lead.create({'name': 'Logged', 'type': 'opportunity',
                                 'expected_revenue': 99000})
        self.assertTrue(self._run_for(lead).x_log_ids)

    # -- the security boundary -------------------------------------------

    def test_a_field_outside_the_whitelist_is_refused(self):
        """The whole reason the whitelist exists.

        Steps run as sudo. Without this, anyone who could edit a step could
        have any field written on the next lead anybody created.
        """
        sneaky = self.Flow.create({
            'x_name': 'Should not be able to do this',
            'x_target_model': 'crm.lead', 'x_trigger_type': 'manual',
            'x_allowed_fields': ''})
        self.Step.create({
            'x_flow_id': sneaky.id, 'x_sequence': 10, 'x_name': 'Rewrite name',
            'x_step_type': 'action', 'x_action_type': 'set_field',
            'x_action_field': 'name', 'x_action_value': 'OWNED'})

        victim = self.Lead.create({'name': 'Untouched', 'type': 'opportunity'})
        run = sneaky.run_for_record(victim)
        victim.invalidate_recordset()

        self.assertEqual(victim.name, 'Untouched')
        self.assertEqual(run.x_status, 'error')
        self.assertIn('not allowed to write',
                      (run.x_log_ids[:1].x_outcome or '').lower())

    def test_a_whitelisted_field_still_writes(self):
        allowed = self.Flow.create({
            'x_name': 'Allowed', 'x_target_model': 'crm.lead',
            'x_trigger_type': 'manual', 'x_allowed_fields': 'name'})
        self.Step.create({
            'x_flow_id': allowed.id, 'x_sequence': 10, 'x_name': 'Rename',
            'x_step_type': 'action', 'x_action_type': 'set_field',
            'x_action_field': 'name', 'x_action_value': 'Renamed'})

        lead = self.Lead.create({'name': 'Before', 'type': 'opportunity'})
        run = allowed.run_for_record(lead)
        lead.invalidate_recordset()
        self.assertEqual(lead.name, 'Renamed')
        self.assertEqual(run.x_status, 'completed')

    def test_employees_cannot_author_flows(self):
        Access = self.env['ir.model.access']
        employee = Access.search([
            ('model_id.model', '=', 'x_samra_flow_step'),
            ('group_id', '=', self.env.ref('base.group_user').id)], limit=1)
        self.assertTrue(employee, "no employee ACL found for flow steps")
        self.assertFalse(employee.perm_write)
        self.assertFalse(employee.perm_create)

    def test_managers_can_author_flows(self):
        manager = self.env['ir.model.access'].search([
            ('model_id.model', '=', 'x_samra_flow_step'),
            ('group_id', '=',
             self.env.ref('sales_team.group_sale_manager').id)], limit=1)
        self.assertTrue(manager.perm_write)

    # -- failure is visible -----------------------------------------------

    def test_a_failing_step_marks_the_run_as_error(self):
        """Not swallowed into the outcome text while the run reports success.

        The prototype did exactly that, which made 'are any runs in error?'
        answer no while every step was failing.
        """
        broken = self.Flow.create({
            'x_name': 'Typo', 'x_target_model': 'crm.lead',
            'x_trigger_type': 'manual', 'x_allowed_fields': 'no_such_field'})
        self.Step.create({
            'x_flow_id': broken.id, 'x_sequence': 10, 'x_name': 'Typo step',
            'x_step_type': 'action', 'x_action_type': 'set_field',
            'x_action_field': 'no_such_field', 'x_action_value': 'x'})
        lead = self.Lead.create({'name': 'Broken', 'type': 'opportunity'})
        self.assertEqual(broken.run_for_record(lead).x_status, 'error')

    def test_a_loop_stops(self):
        loopy = self.Flow.create({
            'x_name': 'Loop', 'x_target_model': 'crm.lead',
            'x_trigger_type': 'manual', 'x_allowed_fields': 'priority'})
        first = self.Step.create({
            'x_flow_id': loopy.id, 'x_sequence': 10, 'x_name': 'A',
            'x_step_type': 'action', 'x_action_type': 'set_field',
            'x_action_field': 'priority', 'x_action_value': '1'})
        second = self.Step.create({
            'x_flow_id': loopy.id, 'x_sequence': 20, 'x_name': 'B',
            'x_step_type': 'action', 'x_action_type': 'set_field',
            'x_action_field': 'priority', 'x_action_value': '0'})
        first.x_next_step = second.id
        second.x_next_step = first.id
        lead = self.Lead.create({'name': 'Looping', 'type': 'opportunity'})
        self.assertEqual(loopy.run_for_record(lead).x_status, 'error')

    # -- ownership and wiring ---------------------------------------------

    def test_the_flow_models_belong_to_this_module(self):
        """state='manual' means no module owns them and upgrades skip them."""
        for name in ('x_samra_flow_definition', 'x_samra_flow_step',
                     'x_samra_flow_instance', 'x_samra_flow_log'):
            row = self.env['ir.model'].search([('model', '=', name)], limit=1)
            self.assertEqual(row.state, 'base', f"{name} is not owned")

    def test_the_server_action_calls_the_packaged_engine(self):
        """Not the inline prototype the live instance was carrying."""
        action = self.env['ir.actions.server'].search(
            [('name', '=', 'Samra Flow Engine - Execute On Lead Create')],
            limit=1)
        self.assertEqual(
            (action.code or '').strip(),
            "env['x_samra_flow_definition'].trigger_for_model(record)")

    def test_the_automation_exists_exactly_once(self):
        """A second rule would run every flow twice on every lead."""
        automation = self.env['base.automation'].search(
            [('name', '=', 'Samra Flow Engine Trigger - Lead Create')])
        self.assertEqual(len(automation), 1)
