# -*- coding: utf-8 -*-
"""Aggregation layer behind the management dashboard.

Every figure the dashboard paints is produced here by grouped ORM reads rather
than by pulling records into the browser and counting them there. Each block
also returns the domain that produced it, so the client can hand that exact
domain to an act_window and drill through to the underlying records -- the
numbers and the drill-down can never disagree, because they come from the same
domain.
"""

from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models

from .samra_metrics import CONFIRMED_STATES

INACTIVE_DAYS = 90

VIP_TIER_ORDER = ['regular', 'vip', 'vvip']
VIP_TIER_LABELS = {'regular': 'Regular', 'vip': 'VIP', 'vvip': 'VVIP'}

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

    @api.model
    def _top_clients(self, domain, limit=8):
        """The customers behind the revenue, each a way into their dossier.

        The dashboard otherwise reports entirely in aggregate -- revenue by
        branch, by salesperson, by tier -- and never names a person. A manager
        looking at a good month wants to know who made it, and clicking the
        answer should land on that customer's profile rather than a list.
        """
        groups = self.env['sale.order']._read_group(
            domain, ['partner_id'], ['amount_total:sum', '__count'])

        ranked = sorted(groups, key=lambda row: row[1] or 0.0, reverse=True)[:limit]
        peak = max((row[1] or 0.0 for row in ranked), default=0.0)
        today = fields.Date.today()

        rows = []
        for partner, total, count in ranked:
            revenue = total or 0.0
            last = partner.x_last_purchase_date
            rows.append({
                'id': partner.id,
                'name': partner.display_name,
                'avatar': f'/web/image/res.partner/{partner.id}/avatar_128',
                'tier': partner.x_vip_tier or 'regular',
                'tier_label': VIP_TIER_LABELS.get(partner.x_vip_tier or 'regular', 'Regular'),
                'revenue': revenue,
                'orders': count,
                'share': (revenue / peak * 100) if peak else 0.0,
                'last_purchase': fields.Date.to_string(last) if last else None,
                'days_inactive': (today - last).days if last else None,
                'at_risk': bool(last) and (today - last).days >= INACTIVE_DAYS,
            })
        return rows

    # ------------------------------------------------------------------
    # Drill-down
    # ------------------------------------------------------------------

    @api.model
    def _breakdown_orders(self, domain, limit):
        orders = self.env['sale.order'].search(domain, order='date_order desc', limit=limit)
        total = sum(orders.mapped('amount_total'))

        by_branch = defaultdict(float)
        by_person = defaultdict(float)
        for order in orders:
            by_branch[order.warehouse_id.display_name or 'Unassigned'] += order.amount_total
            by_person[order.user_id.display_name or 'Unassigned'] += order.amount_total

        return {
            'columns': ['Order', 'Date', 'Customer', 'Branch', 'Salesperson', 'Items', 'Total'],
            'rows': [{
                'id': order.id,
                'model': 'sale.order',
                'cells': [
                    order.name,
                    fields.Date.to_string(order.date_order) if order.date_order else '',
                    order.partner_id.display_name,
                    order.warehouse_id.display_name or '',
                    order.user_id.display_name or '',
                    int(sum(line.product_uom_qty for line in order.order_line
                            if line.product_id and not line.display_type)),
                    order.amount_total,
                ],
                'partner_id': order.partner_id.id,
                'amount': order.amount_total,
            } for order in orders],
            'numeric_from': 5,
            'summary': [
                {'label': 'Orders', 'value': len(orders), 'money': False},
                {'label': 'Total', 'value': total, 'money': True},
                {'label': 'Average', 'value': (total / len(orders)) if orders else 0.0, 'money': True},
                {'label': 'Customers', 'value': len(orders.mapped('partner_id')), 'money': False},
            ],
            'splits': [
                {'title': 'By Branch', 'rows': self._split_rows(by_branch)},
                {'title': 'By Salesperson', 'rows': self._split_rows(by_person)},
            ],
        }

    @api.model
    def _breakdown_leads(self, domain, limit):
        leads = self.env['crm.lead'].search(domain, order='expected_revenue desc', limit=limit)
        total = sum(leads.mapped('expected_revenue'))

        by_stage = defaultdict(float)
        for lead in leads:
            by_stage[lead.stage_id.display_name or 'Unassigned'] += lead.expected_revenue

        return {
            'columns': ['Opportunity', 'Customer', 'Stage', 'Salesperson', 'Expected'],
            'rows': [{
                'id': lead.id,
                'model': 'crm.lead',
                'cells': [
                    lead.name,
                    lead.partner_id.display_name or '',
                    lead.stage_id.display_name or '',
                    lead.user_id.display_name or '',
                    lead.expected_revenue,
                ],
                'partner_id': lead.partner_id.id,
                'amount': lead.expected_revenue,
            } for lead in leads],
            'numeric_from': 4,
            'summary': [
                {'label': 'Opportunities', 'value': len(leads), 'money': False},
                {'label': 'Expected', 'value': total, 'money': True},
                {'label': 'Average', 'value': (total / len(leads)) if leads else 0.0, 'money': True},
            ],
            'splits': [{'title': 'By Stage', 'rows': self._split_rows(by_stage)}],
        }

    @api.model
    def _breakdown_customers(self, domain, limit):
        partners = self.env['res.partner'].search(
            domain, order='x_lifetime_value desc', limit=limit)
        total = sum(partners.mapped('x_lifetime_value'))
        today = fields.Date.today()

        by_tier = defaultdict(float)
        for partner in partners:
            by_tier[VIP_TIER_LABELS.get(partner.x_vip_tier or 'regular', 'Regular')] += \
                partner.x_lifetime_value

        return {
            'columns': ['Customer', 'Tier', 'Salesperson', 'Last Purchase',
                        'Days Inactive', 'Lifetime Value'],
            'rows': [{
                'id': partner.id,
                'model': 'res.partner',
                'cells': [
                    partner.display_name,
                    VIP_TIER_LABELS.get(partner.x_vip_tier or 'regular', 'Regular'),
                    partner.user_id.display_name or '',
                    fields.Date.to_string(partner.x_last_purchase_date)
                    if partner.x_last_purchase_date else 'never',
                    (today - partner.x_last_purchase_date).days
                    if partner.x_last_purchase_date else '',
                    partner.x_lifetime_value,
                ],
                'partner_id': partner.id,
                'amount': partner.x_lifetime_value,
                'tier': partner.x_vip_tier or 'regular',
            } for partner in partners],
            'numeric_from': 4,
            'summary': [
                {'label': 'Customers', 'value': len(partners), 'money': False},
                {'label': 'Lifetime Value', 'value': total, 'money': True},
                {'label': 'Average', 'value': (total / len(partners)) if partners else 0.0,
                 'money': True},
            ],
            'splits': [{'title': 'By Tier', 'rows': self._split_rows(by_tier)}],
        }

    @api.model
    def _split_rows(self, totals):
        """Rank a {label: amount} map and give each row its share of the peak."""
        rows = sorted(
            ({'label': label, 'revenue': amount} for label, amount in totals.items()),
            key=lambda row: row['revenue'], reverse=True)
        peak = max((row['revenue'] for row in rows), default=0.0)
        for row in rows:
            row['share'] = (row['revenue'] / peak * 100) if peak else 0.0
        return rows

    @api.model
    def get_breakdown(self, kind, domain=None, title=None, limit=200):
        """Records behind a dashboard figure, shaped for the breakdown screen.

        The dashboard hands back the same domain that produced the number, so
        the screen and the figure cannot disagree. Rows come pre-formatted
        because this is a presentation surface, not a generic list view -- the
        client should not need to know that a branch lives on warehouse_id.
        """
        handlers = {
            'orders': self._breakdown_orders,
            'leads': self._breakdown_leads,
            'customers': self._breakdown_customers,
        }
        if kind not in handlers:
            raise ValueError(f"Unknown breakdown kind {kind!r}.")

        payload = handlers[kind](domain or [], limit)
        payload.update({
            'kind': kind,
            'title': title or kind.title(),
            'currency': self.env.company.currency_id.name or 'AED',
            'limit': limit,
            'truncated': len(payload['rows']) >= limit,
        })
        return payload

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
            'top_clients': self._top_clients(domain),
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
