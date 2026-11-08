"""Lecture de flux publics documentés (JSON). Chaque élément du flux est une annonce complète.

```yaml
options:
  feed_url: https://agence.example/export/annonces.json   # ou file://chemin/local.json
  items_path: "data.listings"                             # chemin vers la liste (optionnel)
  mapping: { source_ref: "id", price: "prix", surface: "surface", city: "ville", ... }
```

Les champs non mappés gardent le nom du modèle ``RawListing``. Les sous-champs s'écrivent ``a.b``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from ..config import ROOT
from ..models import ListingRef, RawListing
from .base import BaseConnector


def _get_path(obj: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


class FeedConnector(BaseConnector):
    method = "feed"

    def _feed_url(self) -> str:
        url = str(self.options["feed_url"])
        if url.startswith("file://") and not url.startswith("file:///"):
            # Chemin relatif à la racine du dépôt (fixtures, démo)
            url = "file://" + str((ROOT / url[len("file://") :]).resolve())
        return url

    def discover(self) -> Iterator[ListingRef]:
        payload = json.loads(self.ctx.client.get(self._feed_url()).text)
        items = _get_path(payload, self.options["items_path"]) if self.options.get("items_path") else payload
        if not isinstance(items, list):
            raise ValueError("flux invalide : liste d'annonces attendue")
        mapping: dict[str, str] = self.options.get("mapping") or {}
        for item in items:
            values = {
                field: _get_path(item, mapping.get(field, field))
                for field in RawListing.model_fields
                if field not in ("source_id", "parsed_fields")
            }
            values = {k: v for k, v in values.items() if v is not None}
            if "source_ref" not in values or "url" not in values:
                continue
            values["source_ref"] = str(values["source_ref"])
            if values.get("postal_code") is not None:
                values["postal_code"] = str(values["postal_code"])
            raw = RawListing(source_id=self.source.id, **values)
            yield self.make_ref(raw.source_ref, raw.url, postal_code_hint=raw.postal_code, raw=raw)
