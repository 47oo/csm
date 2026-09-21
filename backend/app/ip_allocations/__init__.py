"""F021 IP 地址自动 / 手动分配模块：schemas / repository / service / router。

分配**不是**独立领域对象：其唯一产物是一条现有 IPAddress（R-IP-005），
`cluster_id` 仍只经 `app/ip_addresses/service.py::create_ip_address` 写入。
"""