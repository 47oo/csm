"""F010 BareMetal 关联资源聚合读取的业务行为。

判定顺序固定：**先**经 ``bare_metals.service.get_bare_metal_by_id`` 确认主体
BareMetal 存在且活跃（未命中 → ``404``，这是本模块**唯一**的 404 网关）；
**后**才派生五类关联。

派生只调用各资源既有 repository 的 canonical 过滤函数（``list_active`` 系列），
这些函数在父行缺失时**不抛** ``404``，因此「某类为空 / 某子资源已缺」绝不会让
活跃主体被误判为不存在（本模块刻意不使用会在父缺失时抛 404 的 service 层访问器）。

推导深度固定 ≤3 跳、直线式组合：

- NetworkInterface：``nic.bare_metal_id = B``（1 跳）
- IPAddress：对 B 的每个活跃 NIC 取 ``ip.network_interface_id = N``（2 跳）
- VirtualMachine：``vm.bare_metal_id = B``（1 跳）
- Container：``(BARE_METAL, B)`` ∪ 对每个活跃 VM ``(VIRTUAL_MACHINE, V)``（1~2 跳）
- Service：对 ``R(B) = {B} ∪ {B 的活跃 VM} ∪ {Container 相关集合}`` 的每个载体取
  绑定并集（1~3 跳）

Container / Service 多载体并集按资源 ``id`` 去重；五类 ``items`` 均按 ``id`` 升序。
聚合为非分页完整快照：在既有分页过滤上按 ``total`` 取全循环，不静默截断。

本模块不出现任何软删谓词：活跃过滤只经既有 repository 传递（ADR-0004）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.bare_metals import service as bare_metals_service
from app.common.pagination import MAX_PAGE_SIZE, PageParams
from app.containers.repository import ContainerRepository
from app.containers.schemas import CarrierType, ContainerRead
from app.ip_addresses.repository import IpAddressRepository
from app.ip_addresses.schemas import IpAddressRead
from app.models.container import Container
from app.models.ip_address import IpAddress
from app.models.network_interface import NetworkInterface
from app.models.service import Service
from app.models.virtual_machine import VirtualMachine
from app.network_interfaces.repository import NetworkInterfaceRepository
from app.network_interfaces.schemas import NetworkInterfaceRead
from app.resource_views.schemas import RelatedResourcesRead, RelatedSet
from app.services.repository import ServiceRepository
from app.services.schemas import CarrierRef, ServiceCarrierType, ServiceRead
from app.virtual_machines.repository import VirtualMachineRepository
from app.virtual_machines.schemas import VirtualMachineRead

#: 单次分页读取的窗口大小（沿用既有分页上限）。
_PAGE_SIZE = MAX_PAGE_SIZE


def _snapshot(fetch: Callable[[PageParams], tuple[list[Any], int]]) -> list[Any]:
    """经既有分页过滤枚举**全部**匹配活跃行（完整快照，不静默截断）。

    ``fetch`` **必须**是不会在父行缺失时抛 not-found 的 repository canonical
    过滤函数（如 ``*.repository.list_active``）。
    """
    items, total = fetch(PageParams(page=1, page_size=_PAGE_SIZE))
    collected = list(items)
    page = 2
    while len(collected) < total and items:
        items, _ = fetch(PageParams(page=page, page_size=_PAGE_SIZE))
        collected.extend(items)
        page += 1
    return collected


def _dedupe_ascending(rows: Iterable[Any]) -> list[Any]:
    """按资源 ``id`` 去重，并按 ``id`` 升序返回。"""
    by_id: dict[int, Any] = {}
    for row in rows:
        by_id[row.id] = row
    return sorted(by_id.values(), key=lambda row: row.id)


def _related_container_rows(
    container_repo: ContainerRepository,
    bare_metal_id: int,
    virtual_machines: Sequence[VirtualMachine],
) -> list[Container]:
    """Container 相关集合：载体为 B，或载体为 B 的活跃 VM（含间接）。"""
    direct = _snapshot(
        lambda params: container_repo.list_active(
            params, carrier_type=CarrierType.BARE_METAL, carrier_id=bare_metal_id
        )
    )
    indirect: list[Container] = []
    for virtual_machine in virtual_machines:
        indirect.extend(
            _snapshot(
                lambda params, vm_id=virtual_machine.id: container_repo.list_active(
                    params,
                    carrier_type=CarrierType.VIRTUAL_MACHINE,
                    carrier_id=vm_id,
                )
            )
        )
    return _dedupe_ascending([*direct, *indirect])


def _related_service_rows(
    service_repo: ServiceRepository,
    bare_metal_id: int,
    virtual_machines: Sequence[VirtualMachine],
    containers: Sequence[Container],
) -> list[Service]:
    """Service 相关集合：载体的并集与 R(B) 有交集（含间接），按 id 去重。"""
    related_carriers: list[CarrierRef] = [
        CarrierRef(carrier_type=ServiceCarrierType.BARE_METAL, carrier_id=bare_metal_id)
    ]
    related_carriers.extend(
        CarrierRef(carrier_type=ServiceCarrierType.VIRTUAL_MACHINE, carrier_id=vm.id)
        for vm in virtual_machines
    )
    related_carriers.extend(
        CarrierRef(carrier_type=ServiceCarrierType.CONTAINER, carrier_id=container.id)
        for container in containers
    )

    found: list[Service] = []
    for carrier in related_carriers:
        found.extend(
            _snapshot(
                lambda params, ref=carrier: service_repo.list_active_services_by_carrier(
                    ref.carrier_type, ref.carrier_id, params
                )
            )
        )
    return _dedupe_ascending(found)


def get_related_resources(session: Session, bare_metal_id: int) -> RelatedResourcesRead:
    """返回 BareMetal 上下文的五类关联聚合（唯一 404 网关在主体确认）。"""
    # 唯一 404 网关：主体不存在 / 已逻辑删除 → NotFoundError（在派生之前）。
    bare_metal = bare_metals_service.get_bare_metal_by_id(session, bare_metal_id)

    network_interface_repo = NetworkInterfaceRepository(session)
    ip_address_repo = IpAddressRepository(session)
    virtual_machine_repo = VirtualMachineRepository(session)
    container_repo = ContainerRepository(session)
    service_repo = ServiceRepository(session)

    network_interfaces: list[NetworkInterface] = _dedupe_ascending(
        _snapshot(
            lambda params: network_interface_repo.list_active(params, bare_metal_id=bare_metal.id)
        )
    )

    ip_addresses: list[IpAddress] = _dedupe_ascending(
        ip
        for network_interface in network_interfaces
        for ip in _snapshot(
            lambda params, nic_id=network_interface.id: ip_address_repo.list_active(
                params, network_interface_id=nic_id
            )
        )
    )

    virtual_machines: list[VirtualMachine] = _dedupe_ascending(
        _snapshot(
            lambda params: virtual_machine_repo.list_active(params, bare_metal_id=bare_metal.id)
        )
    )

    containers = _related_container_rows(container_repo, bare_metal.id, virtual_machines)
    services = _related_service_rows(service_repo, bare_metal.id, virtual_machines, containers)

    carriers_by_service = service_repo.carriers_for_services([svc.id for svc in services])

    return RelatedResourcesRead(
        network_interfaces=RelatedSet[NetworkInterfaceRead](
            items=[NetworkInterfaceRead.model_validate(row) for row in network_interfaces],
            total=len(network_interfaces),
        ),
        ip_addresses=RelatedSet[IpAddressRead](
            items=[IpAddressRead.model_validate(row) for row in ip_addresses],
            total=len(ip_addresses),
        ),
        virtual_machines=RelatedSet[VirtualMachineRead](
            items=[VirtualMachineRead.model_validate(row) for row in virtual_machines],
            total=len(virtual_machines),
        ),
        containers=RelatedSet[ContainerRead](
            items=[ContainerRead.from_model(row) for row in containers],
            total=len(containers),
        ),
        services=RelatedSet[ServiceRead](
            items=[
                ServiceRead.from_model(service, carriers_by_service.get(service.id, []))
                for service in services
            ],
            total=len(services),
        ),
    )
