# -*- coding: utf-8 -*-
"""Aggregation layer behind the management dashboard.

Every figure the dashboard paints is produced here by grouped ORM reads rather
than by pulling records into the browser and counting them there. Each block
also returns the domain that produced it, so the client can hand that exact
domain to an act_window and drill through to the underlying records -- the
numbers and the drill-down can never disagree, because they come from the same
domain.
"""

from datetime import timedelta

from odoo import api, fields, models

INACTIVE_DAYS = 90

VIP_TIER_ORDER = ['regular', 'vip', 'vvip']
VIP_TIER_LABELS = {'regular': 'Regular', 'vip': 'VIP', 'vvip': 'VVIP'}

# Orders in these states are real business; drafts and cancellations are not.
CONFIRMED_STATES = ('sale', 'done')


class SamraDashboard(models.AbstractModel):
    _name = 'samra.dashboard'
    _description = 'Samra Management Dashboard Data'

    # ------------------------------------------------------------------
    # Domain construction
    # ------------------------------------------------------------------

    @api.model
    def _order_domain(self, filters):
        domain = [('state', 'in', list(CONFIRMED_STATES))]
        if filters.get('date_from'):
            domain.append(('date_order', '>=', filters['date_from']))
        if filters.get('date_to'):
            domain.append(('date_order', '<=', f"{filters['date_to']} 23:59:59"))
        if filters.get('warehouse_id'):
            domain.append(('warehouse_id', '=', int(filters['warehouse_id'])))
        if filters.get('user_id'):
            domain.append(('user_id', '=', int(filters['user_id'])))
        return domain

    # ------------------------------------------------------------------
    # Blocks
    # ------------------------------------------------------------------

    @api.model
    def _kpis(self, domain):
        groups = self.env['sale.order']._read_group(domain, [], ['amount_total:sum', '__count'])
        revenue, count = (groups[0] if groups else (0.0, 0))
        revenue = revenue or 0.0
        return {
            'revenue': revenue,
            'orders': count,
            'average_order_value': (revenue / count) if count else 0.0,
            'domain': domain,
        }

    @api.model
    def _by_branch(self, domain):
        groups = self.env['sale.order']._read_group(
            domain, ['warehouse_id'], ['amount_total:sum', '__count'])
        rows = [{
            'id': warehouse.id,
            'label': warehouse.display_name or 'Unassigned',
            'revenue': total or 0.0,
            'orders': count,
            'domain': domain + [('warehouse_id', '=', warehouse.id)],
        } for warehouse, total, count in groups]
        rows.sort(key=lambda r: r['revenue'], reverse=True)
        return rows

    @api.model
    def _by_salesperson(self, domain):
        """Requirement 34: per-salesperson revenue, volume and average ticket."""
        groups = self.env['sale.order']._read_group(
            domain, ['user_id'], ['amount_total:sum', '__count'])
        rows = [{
            'id': user.id,
            'label': user.display_name or 'Unassigned',
            'revenue': total or 0.0,
            'orders': count,
            'average_order_value': ((total or 0.0) / count) if count else 0.0,
            'domain': domain + [('user_id', '=', user.id)],
        } for user, total, count in groups]
        rows.sort(key=lambda r: r['revenue'], reverse=True)
        return rows

    @api.model
    def _by_vip_tier(self, domain):
        """Requirement 35: tier composition and each tier's share of revenue.

        sale.order cannot be grouped on a field of its partner, so orders are
        grouped by partner and then folded into tiers.
        """
        groups = self.env['sale.order']._read_group(
            domain, ['partner_id'], ['amount_total:sum', '__count'])

        partner_ids = [partner.id for partner, _total, _count in groups]
        tier_by_partner = {
            partner.id: (partner.x_vip_tier or 'regular')
            for partner in self.env['res.partner'].browse(partner_ids)
        }

        revenue = dict.fromkeys(VIP_TIER_ORDER, 0.0)
        orders = dict.fromkeys(VIP_TIER_ORDER, 0)
        for partner, total, count in groups:
            tier = tier_by_partner.get(partner.id, 'regular')
            revenue[tier] += total or 0.0
            orders[tier] += count

        headcount = {
            (tier or 'regular'): count
            for tier, count in self.env['res.partner']._read_group(
                [('customer_rank', '>', 0)], ['x_vip_tier'], ['__count'])
        }

        total_revenue = sum(revenue.values())
        return [{
            'tier': tier,
            'label': VIP_TIER_LABELS[tier],
            'customers': headcount.get(tier, 0),
            'revenue': revenue[tier],
            'orders': orders[tier],
            'revenue_share': (revenue[tier] / total_revenue * 100) if total_revenue else 0.0,
            'domain': [('customer_rank', '>', 0), ('x_vip_tier', '=', tier)]
                      if tier != 'regular'
                      else [('customer_rank', '>', 0), ('x_vip_tier', 'in', [False, 'regular'])],
        } for tier in VIP_TIER_ORDER]

    @api.model
    def _pipeline(self, filters):
        """Requirement 11: the seven-stage funnel, each stage clickable."""
        domain = [('active', '=', True), ('type', '=', 'opportunity')]
        if filters.get('user_id'):
            domain.append(('user_id', '=', int(filters['user_id'])))

        groups = self.env['crm.lead']._read_group(
            domain, ['stage_id'], ['expected_revenue:sum', '__count'])

        rows = [{
            'id': stage.id,
            'label': stage.display_name,
            'sequence': stage.sequence,
            'leads': count,
            'expected_revenue': total or 0.0,
            'domain': domain + [('stage_id', '=', stage.id)],
        } for stage, total, count in groups]
        rows.sort(key=lambda r: r['sequence'])

        peak = max((r['leads'] for r in rows), default=0)
        for row in rows:
            row['width'] = (row['leads'] / peak * 100) if peak else 0.0
        return rows

    @api.model
    def _reactivation(self):
        """Requirement 18/36: customers gone quiet, as an actionable list."""
        cutoff = fields.Date.today() - timedelta(days=INACTIVE_DAYS)
        domain = [
            ('customer_rank', '>', 0),
            '|',
            ('x_last_purchase_date', '=', False),
            ('x_last_purchase_date', '<', fields.Date.to_string(cutoff)),
        ]
        partners = self.env['res.partner'].search(
            domain, order='x_lifetime_value desc', limit=15)
        today = fields.Date.today()
        return {
            'count': self.env['res.partner'].search_count(domain),
            'domain': domain,
            'cutoff_days': INACTIVE_DAYS,
            'customers': [{
                'id': partner.id,
                'name': partner.display_name,
                'tier': partner.x_vip_tier or 'regular',
                'lifetime_value': partner.x_lifetime_value,
                'last_purchase': fields.Date.to_string(partner.x_last_purchase_date)
                                 if partner.x_last_purchase_date else None,
                'days_inactive': (today - partner.x_last_purchase_date).days
                                 if partner.x_last_purchase_date else None,
            } for partner in partners],
        }

    @api.model
    def _loyalty(self):
        if 'loyalty.card' not in self.env:
            return {'available': False}

        cards = self.env['loyalty.card'].search([])
        outstanding = sum(cards.mapped('points'))

        redeemed = 0.0
        if 'loyalty.history' in self.env:
            groups = self.env['loyalty.history']._read_group([], [], ['used:sum'])
            redeemed = (groups[0][0] if groups else 0.0) or 0.0

        return {
            'available': True,
            'members': len(cards),
            'points_outstanding': outstanding,
            'points_redeemed': redeemed,
            'domain': [],
        }

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    @api.model
    def get_dashboard_data(self, filters=None):
        filters = filters or {}
        domain = self._order_domain(filters)

        return {
            'filters': filters,
            'currency': self.env.company.currency_id.name or 'AED',
            'kpis': self._kpis(domain),
            'branches': self._by_branch(domain),
            'salespeople': self._by_salesperson(domain),
            'vip': self._by_vip_tier(domain),
            'pipeline': self._pipeline(filters),
            'reactivation': self._reactivation(),
            'loyalty': self._loyalty(),
        }

    @api.model
    def get_filter_options(self):
        """Branches and salespeople available to filter on."""
        return {
            'branches': [{'id': w.id, 'name': w.display_name}
                         for w in self.env['stock.warehouse'].search([])],
            'salespeople': [{'id': u.id, 'name': u.display_name}
                            for u in self.env['res.users'].search(
                                [('share', '=', False)], order='name')],
        }
