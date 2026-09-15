"""资源 ORM 模型：每类资源一个独立模块、一张独立表。

导入该包即注册全部模型到 ``Base.metadata``（Alembic ``env.py`` 与结构 guard
测试依赖此行为）。**不存在**通用 Resource 基类 / 多态映射。
"""

from app.models.cluster import Cluster

__all__ = ["Cluster"]
