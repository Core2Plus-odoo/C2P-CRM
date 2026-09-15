# -*- coding: utf-8 -*-
"""Customer transfer between salespeople, with an audit entry.

Requirement 21 asks that authorised managers move customers between associates
while retaining full history, and requirement 40 asks that transfers be
auditable. Editing `user_id` on the contact form does the first but not the
second: the change lands in the record and nothing says who decided it or why.

Nothing is copied or re-parented here. The customer record is the history, so
reassignment is a change of owner, not a migration.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SamraCustomerTransfer(models.TransientModel):
    _name = 'samra.customer.transfer'
    _description = 'Transfer Customers Between Salespeople'

    partner_ids = fields.Many2many('res.partner', string='Customers', required=True)
    from_user_id = fields.Many2one('res.users', string='Current Salesperson', readonly=True)
    to_user_id = fields.Many2one(
        'res.users', string='New Salesperson', required=True,
        domain="[('share', '=', False)]",
    )
    reason = fields.Text(
        string='Reason',
        required=True,
        help='Recorded against every customer moved. Required because a '
             'transfer without a stated reason is not an audit trail.',
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        partner_ids = self.env.context.get('active_ids') or []
        if partner_ids and self.env.context.get('active_model') == 'res.partner':
            partners = self.env['res.partner'].browse(partner_ids)
            values['partner_ids'] = partners.ids
            owners = partners.mapped('user_id')
            if len(owners) == 1:
                values['from_user_id'] = owners.id
        return values

    def action_transfer(self):
        self.ensure_one()

        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_(
                "Only Sales managers can transfer customers between salespeople."))

        if not self.partner_ids:
            raise UserError(_("Select at least one customer to transfer."))

        for partner in self.partner_ids:
            previous = partner.user_id
            if previous == self.to_user_id:
                continue

            partner.user_id = self.to_user_id

            # The chatter is the audit trail: it carries who acted, when, and
            # why, next to the record it describes.
            partner.message_post(body=_(
                "Customer transferred from %(old)s to %(new)s by %(actor)s.<br/>"
                "Reason: %(reason)s",
                old=previous.display_name or _("unassigned"),
                new=self.to_user_id.display_name,
                actor=self.env.user.display_name,
                reason=self.reason,
            ))

        return {'type': 'ir.actions.act_window_close'}
