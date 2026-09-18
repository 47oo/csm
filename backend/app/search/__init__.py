"""F018 集群内资源关键字搜索（只读）。

模块归属：**不放进** ``resource_views``（F010 的源码 token guard 禁止
``cluster_id`` 等 token，而搜索需要 Cluster 范围过滤）。依赖方向单向：
``search → resource_views``，``resource_views`` 不感知 ``search``。
"""
