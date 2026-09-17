"""资源 ORM 模型：每类资源一个独立模块、一张独立表。

导入该包即注册全部模型到 ``Base.metadata``（Alembic ``env.py`` 与结构 guard
测试依赖此行为）。**不存在**通用 Resource 基类 / 多态映射。

``users`` / ``sessions`` 是认证表（F013），**不是** Resource，也**不进入**资源
分类体系。
"""

from app.models.bare_metal import BareMetal
from app.models.cluster import Cluster
from app.models.container import Container
from app.models.ip_address import IpAddress
from app.models.network_interface import NetworkInterface
from app.models.service import Service
from app.models.service_carrier import ServiceCarrier
from app.models.session import Session
from app.models.user import User
from app.models.virtual_machine import VirtualMachine

__all__ = [
    "BareMetal",
    "Cluster",
    "Container",
    "IpAddress",
    "NetworkInterface",
    "Service",
    "ServiceCarrier",
    "Session",
    "User",
    "VirtualMachine",
]
