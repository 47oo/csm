"""F021 分配 HTTP 路由（``docs/api/f021-ip-address-allocation.md`` §3）。

恰 2 个端点，均位于 ``/api`` 前缀下（由 ``app.main`` 挂载），供 F013 的 ``/api/*``
认证中间件自动覆盖，无需白名单。成功 ``201``，响应复用 F005 的 ``IpAddressRead``
（恰 5 字段，无 ``cluster_id`` / ``status`` / ``deleted_at``）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.ip_addresses.schemas import IpAddressRead
from app.ip_allocations import service
from app.ip_allocations.schemas import (
    IpAddressAutoAllocateRequest,
    IpAddressManualAllocateRequest,
)

router = APIRouter(prefix="/ip-addresses", tags=["ip-address-allocations"])

SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post("/allocate", response_model=IpAddressRead, status_code=status.HTTP_201_CREATED)
def allocate_ip_address(
    payload: IpAddressAutoAllocateRequest, session: SessionDep
) -> IpAddressRead:
    ip = service.allocate_ip_auto(session, payload)
    return IpAddressRead.model_validate(ip)


@router.post(
    "/allocate-manual", response_model=IpAddressRead, status_code=status.HTTP_201_CREATED
)
def allocate_ip_address_manual(
    payload: IpAddressManualAllocateRequest, session: SessionDep
) -> IpAddressRead:
    ip = service.allocate_ip_manual(session, payload)
    return IpAddressRead.model_validate(ip)