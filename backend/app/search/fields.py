"""F018 可匹配字段清单（契约 §2 的**唯一权威**在
``docs/api/f018-cluster-keyword-search.md``）。

``SEARCHABLE_FIELDS`` 的键顺序即 ``resource_type`` 的物化 rank；每个元组的顺序即
``matched_fields`` 的输出顺序。**仅**列入契约 §2 的字段：关系外键、资源状态字段、
时间戳、``carriers`` 一概不参与匹配。
"""

from __future__ import annotations

from app.search.schemas import SearchResourceType

SEARCHABLE_FIELDS: dict[SearchResourceType, tuple[str, ...]] = {
    SearchResourceType.BARE_METAL: (
        "hostname",
        "vendor",
        "model",
        "serial_number",
        "cpu",
        "memory",
        "gpu",
        "storage",
    ),
    SearchResourceType.NETWORK_INTERFACE: (
        "name",
        "technology_type",
        "purpose",
    ),
    SearchResourceType.IP_ADDRESS: ("ip_address",),
    SearchResourceType.VIRTUAL_MACHINE: (
        "name",
        "cpu",
        "memory",
        "disk",
        "os",
        "hypervisor",
        "owner",
    ),
    SearchResourceType.CONTAINER: (
        "name",
        "image",
        "cpu",
        "memory",
        "owner",
    ),
    SearchResourceType.SERVICE: (
        "name",
        "service_type",
        "url",
        "port",
        "protocol",
        "owner",
        "description",
    ),
}
