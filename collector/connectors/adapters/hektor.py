"""Adaptateur pour les sites d'agence propulsés par Hektor (LBI) : Act'Immo, Coeuret Immobilier…

Pas de données structurées : l'extraction est celle du connecteur ``html`` (sélecteurs CSS dans
``options.fields``, un jeu par thème). Cet adaptateur ajoute un cas observé le 2026-11-09 :

* sur beaucoup de fiches, le prix du bandeau est **vide** et seul le bloc « Financier » donne le
  « Prix net vendeur ». Le prix acheteur est alors reconstitué comme
  ``net × (1 + taux d'honoraires à la charge de l'acquéreur)`` (taux lu dans le texte « x,xx % d'honoraires
  TTC à la charge de l'acquéreur »), arrondi à 100 €. Vérifié sur une fiche complète : 280 000 € net × 1,0536
  = 295 008 € pour un prix affiché de 295 000 €. Sans taux d'honoraires lisible, le prix reste inconnu
  (on ne publie pas un prix net vendeur comme prix d'achat). Le champ est marqué « parsed ».
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ...models import ListingRef, RawListing
from ...textparse import parse_number
from ..html import HtmlConnector

NET_PRICE = ".title_finance:-soup-contains('Prix net vendeur') + .price_finance"
FEE_RATE = re.compile(r"([\d]+(?:[.,]\d+)?)\s*%\s*d[’']?\s*honoraires", re.I)


def derived_buyer_price(html: str) -> float | None:
    """Prix acheteur reconstitué depuis le prix net vendeur et le taux d'honoraires, sinon ``None``."""
    soup = BeautifulSoup(html, "lxml")
    node = soup.select_one(NET_PRICE)
    net = parse_number(node.get_text(" ", strip=True)) if node else None
    rate = FEE_RATE.search(soup.get_text(" ", strip=True))
    if not net or not rate:
        return None
    pct = parse_number(rate.group(1))
    return round(net * (1 + pct / 100), -2) if pct is not None and 0 <= pct < 20 else None


class HektorConnector(HtmlConnector):
    method = "adapter:hektor"

    def parse_detail(self, html: str, ref: ListingRef) -> RawListing | None:
        raw = super().parse_detail(html, ref)
        if raw is not None and not raw.price and (price := derived_buyer_price(html)):
            raw.price = price
            raw.parsed_fields = [*raw.parsed_fields, "price"]
        return raw
