# -*- coding: utf-8 -*-
"""What to show this customer next.

Requirement 14 asks for cross-sell. The hard part of a recommendation on a
shop floor is not picking a product -- it is picking one the associate will
actually say out loud. A bare list of SKUs gets ignored, because the person
holding it cannot tell whether the machine knows something or is guessing.

So every recommendation carries the reason it exists, in the words an
associate would use: "On her wishlist since March", "Viewed twice, never
bought", "Bought by others who bought her Heritage bangle". The reason is not
decoration. It is what makes the suggestion sayable, and it is what lets the
associate discard a bad one in half a second instead of losing trust in the
whole panel.

Five signals in two classes. INTENT is something the customer did about this
specific piece -- put it on her wishlist, asked to see it across the counter.
INFERRED is something we worked out about her -- people like her buy this, it
is in the collection she favours, it is the category she spends in.

Ranking is lexicographic, not a single total: any piece with intent evidence
outranks any piece without it, and inferred score only breaks ties. That
matters because inferred signals stack. A piece can be co-purchased AND in her
collection AND in her category, and three weak inferences summed will beat one
strong fact if you let them share a scale. They should not: a woman who asked
to see a ring twice is closer to buying it than a statistical neighbour is.
Within a class scores do add, and the reasons add with them, so a piece that
is both wishlisted and popular ranks above one that is only wishlisted -- and
says so.

Deliberately not machine learning. A jeweller has hundreds of customers and
thousands of pieces, which is far too little data to train anything honest,
and a model that cannot explain itself would fail the sayability test above.
These are rules a salesperson would recognise as their own reasoning.
"""

from collections import defaultdict

from odoo import api, fields, models

from .samra_metrics import CONFIRMED_STATES

# How many to return. More than about six and the panel stops being a
# suggestion and becomes another catalogue to search.
TOP_N = 6

# Intent: she did something about this exact piece.
SCORE_WISHLIST = 100.0
SCORE_VIEWED = 60.0

# Inferred: we worked it out. Never compared against the scores above.
SCORE_SIMILAR = 45.0
SCORE_COLLECTION = 30.0
SCORE_CATEGORY = 20.0

INTENT, INFERRED = 'intent', 'inferred'

# A piece far outside what someone has ever spent is not a recommendation,
# it is a fantasy. Anything beyond this multiple of their typical ticket is
# dropped; anything comfortably inside it gets a nudge.
BUDGET_CEILING = 2.5
BUDGET_BONUS = 15.0

# How far back co-purchase evidence is drawn from, in orders.
SIMILAR_ORDER_SAMPLE = 400


class ResPartnerRecommendations(models.Model):
    _inherit = 'res.partner'

    # ------------------------------------------------------------------
    # What the customer already has or has asked for
    # ------------------------------------------------------------------

    def _samra_owned_product_ids(self):
        """Products already bought. Never recommend one of these again.

        Jewellery is not groceries: a second identical ring is not a repeat
        purchase, it is an embarrassing suggestion.
        """
        self.ensure_one()
        lines = self.env['sale.order.line'].search([
            ('order_id.partner_id', '=', self.id),
            ('order_id.state', 'in', list(CONFIRMED_STATES)),
        ])
        return set(lines.mapped('product_id').ids)

    def _samra_budget(self):
        """What this customer typically spends on one piece.

        Their stated budget preference wins when set, because it is the one
        figure they actually told us. Otherwise infer it from the average
        line, not the average order -- a customer who buys three pieces at
        once has not tripled their taste.
        """
        self.ensure_one()
        if self.x_budget_pref:
            return self.x_budget_pref

        lines = self.env['sale.order.line'].search([
            ('order_id.partner_id', '=', self.id),
            ('order_id.state', 'in', list(CONFIRMED_STATES)),
            ('product_id', '!=', False),
        ])
        prices = [line.price_unit for line in lines if line.price_unit > 0]
        return (sum(prices) / len(prices)) if prices else 0.0

    # ------------------------------------------------------------------
    # The signals
    # ------------------------------------------------------------------

    def _samra_signal_wishlist(self, owned):
        """Asked for by name and still not bought. The strongest signal there is."""
        self.ensure_one()
        out = []
        entries = self.env['x_samra_wishlist'].search(
            [('x_partner_id', '=', self.id)], order='x_date_added desc')
        for entry in entries:
            product = entry.x_product_id
            if not product or product.id in owned:
                continue
            since = (f"since {fields.Date.to_string(entry.x_date_added)}"
                     if entry.x_date_added else "")
            reason = f"On the wishlist {since}".strip()
            out.append((product, INTENT, SCORE_WISHLIST, reason))
        return out

    def _samra_signal_viewed(self, owned, wishlisted):
        """Shown in store, walked away. Interest without a decision."""
        self.ensure_one()
        counts = defaultdict(int)
        products = {}
        for record in self.env['x_samra_viewed_product'].search(
                [('x_partner_id', '=', self.id)]):
            product = record.x_product_id
            if not product or product.id in owned or product.id in wishlisted:
                continue
            counts[product.id] += 1
            products[product.id] = product

        out = []
        for product_id, seen in counts.items():
            reason = ("Viewed once, never bought" if seen == 1
                      else f"Viewed {seen} times, never bought")
            # A second viewing is a much stronger signal than a first.
            out.append((products[product_id], INTENT,
                        SCORE_VIEWED + (seen - 1) * 10, reason))
        return out

    def _samra_signal_similar(self, owned):
        """Bought by people who bought what this customer bought.

        Plain co-purchase over confirmed orders. Restricted to a recent sample
        so the query stays bounded on a growing database, and so last year's
        fashion does not outvote this season's.
        """
        self.ensure_one()
        if not owned:
            return []

        peer_lines = self.env['sale.order.line'].search([
            ('product_id', 'in', list(owned)),
            ('order_id.partner_id', '!=', self.id),
            ('order_id.state', 'in', list(CONFIRMED_STATES)),
        ], limit=SIMILAR_ORDER_SAMPLE)
        peers = peer_lines.mapped('order_id.partner_id')
        if not peers:
            return []

        # The piece of theirs that earned each peer, so the reason can name it.
        anchor_by_peer = {}
        for line in peer_lines:
            anchor_by_peer.setdefault(line.order_id.partner_id.id, line.product_id)

        counts = defaultdict(int)
        anchors = {}
        products = {}
        for line in self.env['sale.order.line'].search([
            ('order_id.partner_id', 'in', peers.ids),
            ('order_id.state', 'in', list(CONFIRMED_STATES)),
            ('product_id', '!=', False),
        ], limit=SIMILAR_ORDER_SAMPLE * 4):
            product = line.product_id
            if product.id in owned:
                continue
            counts[product.id] += 1
            products[product.id] = product
            anchors.setdefault(product.id, anchor_by_peer.get(line.order_id.partner_id.id))

        out = []
        for product_id, weight in counts.items():
            anchor = anchors.get(product_id)
            reason = (f"Bought by others who bought {anchor.display_name}"
                      if anchor else "Popular with similar customers")
            out.append((products[product_id], INFERRED,
                        SCORE_SIMILAR + min(weight, 5) * 3, reason))
        return out

    def _samra_signal_preferences(self, owned):
        """Their stated taste, matched against the catalogue.

        Preference fields are free text filled in by an associate, so they are
        matched loosely. An exact-match lookup on a field somebody typed by
        hand would return nothing and quietly make the whole signal dead.
        """
        self.ensure_one()
        out = []
        Product = self.env['product.product']

        if self.x_collection_pref:
            for product in Product.search([
                ('sale_ok', '=', True),
                ('x_collection', 'ilike', self.x_collection_pref),
                ('id', 'not in', list(owned)),
            ], limit=12):
                out.append((product, INFERRED, SCORE_COLLECTION,
                            f"{self.x_collection_pref} collection, her preference"))

        if self.x_gemstone_pref:
            for product in Product.search([
                ('sale_ok', '=', True),
                ('x_gemstone', 'ilike', self.x_gemstone_pref),
                ('id', 'not in', list(owned)),
            ], limit=12):
                out.append((product, INFERRED, SCORE_COLLECTION,
                            f"Set with {self.x_gemstone_pref}, her preference"))

        if self.x_style_pref:
            for product in Product.search([
                ('sale_ok', '=', True),
                ('x_style', 'ilike', self.x_style_pref),
                ('id', 'not in', list(owned)),
            ], limit=12):
                out.append((product, INFERRED, SCORE_COLLECTION,
                            f"{self.x_style_pref} style, her preference"))
        return out

    def _samra_signal_category(self, owned):
        """More of what they demonstrably buy, from the category they buy most."""
        self.ensure_one()
        if not owned:
            return []

        spend = defaultdict(float)
        for product in self.env['product.product'].browse(list(owned)).exists():
            if product.categ_id:
                spend[product.categ_id] += product.list_price

        if not spend:
            return []
        top = max(spend, key=spend.get)

        return [(product, INFERRED, SCORE_CATEGORY, f"More from {top.display_name}")
                for product in self.env['product.product'].search([
                    ('sale_ok', '=', True),
                    ('categ_id', '=', top.id),
                    ('id', 'not in', list(owned)),
                ], limit=12)]

    # ------------------------------------------------------------------
    # Putting it together
    # ------------------------------------------------------------------

    def _samra_recommendations(self, limit=TOP_N):
        """Rank the signals into a list an associate can read aloud."""
        self.ensure_one()

        owned = self._samra_owned_product_ids()
        wishlisted = set(self.env['x_samra_wishlist'].search(
            [('x_partner_id', '=', self.id)]).mapped('x_product_id').ids)
        budget = self._samra_budget()

        intent = defaultdict(float)
        inferred = defaultdict(float)
        reasons = defaultdict(list)
        products = {}

        for product, kind, score, reason in (
            self._samra_signal_wishlist(owned)
            + self._samra_signal_viewed(owned, wishlisted)
            + self._samra_signal_similar(owned)
            + self._samra_signal_preferences(owned)
            + self._samra_signal_category(owned)
        ):
            products[product.id] = product
            (intent if kind == INTENT else inferred)[product.id] += score
            if reason and reason not in reasons[product.id]:
                reasons[product.id].append(reason)

        rows = []
        for product_id in products:
            product = products[product_id]
            price = product.list_price or 0.0

            if budget and price > budget * BUDGET_CEILING:
                # Out of reach. Suggesting it wastes the associate's attention
                # and risks embarrassing the customer.
                continue

            # Budget fit is a hint about us, not an act of hers, so it lands
            # on the inferred score where it cannot jump the intent ordering.
            fit = BUDGET_BONUS if (budget and price <= budget * 1.2) else 0.0

            rows.append({
                'id': product.id,
                'name': product.display_name,
                'sku': product.default_code or '',
                'price': price,
                # Joined here rather than in the template: a product with no
                # gemstone or no SKU would otherwise render a dangling
                # separator, and QWeb has no clean way to drop one.
                'meta': ' · '.join(part for part in (
                    product.x_collection or '',
                    product.x_gemstone or '',
                    f"{product.x_gold_weight:g}g" if product.x_gold_weight else '',
                    product.default_code or '',
                ) if part),
                'intent': round(intent[product_id], 1),
                'score': round(inferred[product_id] + fit, 1),
                'reasons': reasons[product_id][:2],
            })

        # Lexicographic: intent first, and only then how much we inferred.
        rows.sort(key=lambda row: (-row['intent'], -row['score'], row['name']))
        return {
            'budget': budget,
            'considered': len(products),
            'products': rows[:limit],
        }

    @api.model
    def samra_recommendations(self, partner_id, limit=TOP_N):
        """Callable entry point, for the POS as well as the backend profile."""
        return self.browse(int(partner_id))._samra_recommendations(limit=limit)
