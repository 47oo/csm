"""F013 global search schemas (Contract §2).

The search response is a list of discriminated ``SearchItem`` rows keyed by
``object_type``; every row carries a stable UUID ``id``, the ``matched_field``/
``matched_value`` and exactly one populated typed object (``resource``,
``cluster``, ``ip_address`` or ``service``). ``ip_address``/``service`` rows may
additionally embed the owning ``resource``. The field set never varies with the
query so the frontend can discriminate deterministically.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel

DeletedMode = Literal["exclude", "include", "only"]
ObjectType = Literal["resource", "cluster", "ip_address", "service"]
MatchedField = Literal["hostname", "address", "code", "name"]


class SearchClusterNested(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class SearchRelatedInterface(BaseModel):
    """Interface projection inside ``resource.related`` (F018, Contract §2.9)."""

    id: uuid.UUID
    name: str
    interface_type: str


class SearchRelatedIPAddress(BaseModel):
    """IPAddress projection inside ``resource.related`` (F018, Contract §2.9)."""

    id: uuid.UUID
    address: str


class SearchResourceRelated(BaseModel):
    """One bound-IP association row (F018, Contract §2.9).

    The row identity is the IPAddress ``id`` (stable ID, ordering tie-break).
    Only IPs bound to an Interface appear; unbound IPs (``interface_id IS NULL``)
    never produce a row.
    """

    id: uuid.UUID
    interface: SearchRelatedInterface
    ip_address: SearchRelatedIPAddress
    network: SearchNetworkNested


class SearchResourceObject(BaseModel):
    id: uuid.UUID
    hostname: str
    resource_type: str
    role: str
    status: str
    cluster: SearchClusterNested
    # F018 fixed superset: populated only on ``object_type="resource"`` rows
    # (``related=[]`` / ``related_total=0`` when there is no association); the
    # nested ``resource`` of non-resource rows keeps both as ``null``.
    related: list[SearchResourceRelated] | None = None
    related_total: int | None = None


class SearchClusterObject(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: str


class SearchNetworkNested(BaseModel):
    id: uuid.UUID
    name: str


class SearchInterfaceNested(BaseModel):
    id: uuid.UUID
    name: str


class SearchIPAddressObject(BaseModel):
    id: uuid.UUID
    address: str
    network: SearchNetworkNested
    interface: SearchInterfaceNested | None


class SearchServiceObject(BaseModel):
    id: uuid.UUID
    name: str
    status: str


class SearchItem(BaseModel):
    object_type: ObjectType
    id: uuid.UUID
    matched_field: MatchedField
    matched_value: str
    resource: SearchResourceObject | None = None
    cluster: SearchClusterObject | None = None
    ip_address: SearchIPAddressObject | None = None
    service: SearchServiceObject | None = None


class SearchListResponse(BaseModel):
    items: list[SearchItem]
    page: int
    page_size: int
    total: int