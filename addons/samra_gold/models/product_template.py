# -*- coding: utf-8 -*-
"""Weight, purity and making charge on the product, and the price they produce.

The arithmetic a jeweller does on a calculator, written down once:

    net     = gross - stones
    metal   = net x rate(karat) x (1 + wastage)
    price   = metal + making + stone value

Making charge is three different commercial models in one field pair, because
shops really do use all three: per gram for plain gold, a flat fee for a
standard setting, and a percentage of metal value for higher-end pieces where
the labour scales with what it is working on.

Everything here is stored and computed, not related, so a price survives the
rate table being edited afterwards -- a quotation printed last Tuesday should
not silently reprice when somebody corrects Wednesday's figure.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .samra_gold_rate import KARAT_SELECTION, PURITY

MAKING_CHARGE_TYPES = [
    ('per_gram', 'Per Gram'),
    ('flat', 'Flat Amount'),
    ('percent', '% of Metal Value'),
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    x_is_gold = fields.Boolean(
        string='Gold Item',
        help='Price this product from the daily gold rate rather than by hand.')

    x_karat = fields.Selection(
        KARAT_SELECTION, string='Karat', default='22',
        help='Purity of the metal. 21K is the Gulf retail standard; 22K the '
             'Indian one.')

    # Weights are grams throughout. product.template.weight is deliberately
    # left alone: it is the shipping weight in the system UoM, and overloading
    # it would make delivery and this module fight over the same column.
    x_gross_weight = fields.Float(
        string='Gross Weight (g)', digits=(12, 3),
        help='Total weight of the finished piece, stones included.')
    x_stone_weight = fields.Float(
        string='Stone Weight (g)', digits=(12, 3),
        help='Weight of stones, subtracted to find the metal actually present.')
    x_net_weight = fields.Float(
        string='Net Gold (g)', digits=(12, 3),
        compute='_compute_x_net_weight', store=True,
        help='Gross less stones: the metal the rate is charged on.')
    x_fine_weight = fields.Float(
        string='Fine Gold (g)', digits=(12, 3),
        compute='_compute_x_net_weight', store=True,
        help='Net weight expressed as pure gold. This is the figure that '
             'aggregates meaningfully across karats -- adding 5g of 18K to 5g '
             'of 22K is not 10g of anything.')

    x_wastage_pct = fields.Float(
        string='Wastage %', digits=(5, 2),
        help='Metal lost in manufacture, charged to the customer. 8 means 8%.')

    x_making_charge_type = fields.Selection(
        MAKING_CHARGE_TYPES, string='Making Charge', default='per_gram')
    x_making_charge = fields.Float(
        string='Making Charge Value', digits='Product Price',
        help='Read according to the type: currency per gram, a flat amount, '
             'or a percentage of metal value.')

    x_stone_value = fields.Float(
        string='Stone Value', digits='Product Price',
        help='Cost of the stones, added after the metal calculation.')

    # Breakdown, computed live so the form shows its own working. Not stored:
    # these move with the rate, and a stored copy would be stale by morning.
    x_gold_rate_used = fields.Float(
        string='Rate Applied', digits='Product Price',
        compute='_compute_x_gold_breakdown')
    x_metal_value = fields.Float(
        string='Metal Value', digits='Product Price',
        compute='_compute_x_gold_breakdown')
    x_making_value = fields.Float(
        string='Making Value', digits='Product Price',
        compute='_compute_x_gold_breakdown')
    x_computed_price = fields.Float(
        string='Computed Price', digits='Product Price',
        compute='_compute_x_gold_breakdown',
        help="What today's rate makes this piece worth. The Sales Price only "
             "matches once the rate has been applied.")
    x_price_is_stale = fields.Boolean(
        string='Price Out of Date', compute='_compute_x_gold_breakdown',
        help='Set when the sales price no longer matches the current rate.')

    # ------------------------------------------------------------------

    @api.depends('x_gross_weight', 'x_stone_weight', 'x_karat')
    def _compute_x_net_weight(self):
        for product in self:
            net = (product.x_gross_weight or 0.0) - (product.x_stone_weight or 0.0)
            product.x_net_weight = max(net, 0.0)
            product.x_fine_weight = product.x_net_weight * PURITY.get(
                product.x_karat, 0.0)

    @api.constrains('x_gross_weight', 'x_stone_weight')
    def _check_weights(self):
        for product in self:
            if product.x_stone_weight > product.x_gross_weight:
                raise ValidationError(_(
                    "Stones cannot weigh more than the whole piece: %(name)s "
                    "has %(stone)sg of stones in %(gross)sg gross.",
                    name=product.display_name,
                    stone=product.x_stone_weight, gross=product.x_gross_weight))
            if product.x_gross_weight < 0 or product.x_stone_weight < 0:
                raise ValidationError(_("Weights cannot be negative."))

    @api.depends('x_is_gold', 'x_karat', 'x_net_weight', 'x_wastage_pct',
                 'x_making_charge_type', 'x_making_charge', 'x_stone_value',
                 'list_price')
    def _compute_x_gold_breakdown(self):
        Rate = self.env['samra.gold.rate']
        rates = {}
        for product in self:
            if not product.x_is_gold:
                product.x_gold_rate_used = 0.0
                product.x_metal_value = 0.0
                product.x_making_value = 0.0
                product.x_computed_price = 0.0
                product.x_price_is_stale = False
                continue

            karat = product.x_karat
            if karat not in rates:
                rates[karat] = Rate._rate_for(karat)
            rate = rates[karat]

            parts = product._samra_gold_parts(rate=rate)
            product.x_gold_rate_used = rate
            product.x_metal_value = parts['metal']
            product.x_making_value = parts['making']
            product.x_computed_price = parts['total']
            product.x_price_is_stale = (
                rate > 0 and abs((product.list_price or 0.0) - parts['total']) > 0.005)

    # ------------------------------------------------------------------
    # The arithmetic itself
    # ------------------------------------------------------------------

    def _samra_gold_parts(self, rate=None):
        """Break a price into metal, making and stones.

        Returned as parts rather than a total because an invoice line has to
        show them separately: UAE VAT treats making charges differently from
        investment-grade metal, and a customer asking "why is it that much"
        is asking for exactly this breakdown.
        """
        self.ensure_one()
        if rate is None:
            rate = self.env['samra.gold.rate']._rate_for(self.x_karat)

        net = self.x_net_weight or 0.0
        wastage = 1.0 + ((self.x_wastage_pct or 0.0) / 100.0)
        metal = net * (rate or 0.0) * wastage

        if self.x_making_charge_type == 'flat':
            making = self.x_making_charge or 0.0
        elif self.x_making_charge_type == 'percent':
            making = metal * ((self.x_making_charge or 0.0) / 100.0)
        else:
            making = net * (self.x_making_charge or 0.0)

        stones = self.x_stone_value or 0.0
        return {
            'rate': rate or 0.0,
            'metal': metal,
            'making': making,
            'stones': stones,
            'total': metal + making + stones,
        }

    def _samra_gold_price(self, rate=None):
        self.ensure_one()
        return self._samra_gold_parts(rate=rate)['total']

    # ------------------------------------------------------------------

    def action_samra_reprice(self):
        """Reprice the selected products from the current rate.

        The per-product counterpart to applying a rate: useful after editing a
        weight or a making charge, where waiting for tomorrow's rate run would
        leave a wrong price on the shelf all day.
        """
        repriced = 0
        for product in self.filtered('x_is_gold'):
            price = product._samra_gold_price()
            if price > 0 and abs((product.list_price or 0.0) - price) > 0.005:
                product.list_price = price
                repriced += 1
        return repriced
