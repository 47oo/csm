"""F015 T-05 — locale / encoding / 大小写敏感直连断言（AC-09⑥，架构 Risk #1）。

绕过应用层直接对 PostgreSQL 执行 SQL；生产部署文档要求对**已部署**数据库执行同一
断言（见 ``docs/deployment/csm-v1-internal-deployment.md`` §6）。

说明：本测试库可能由宿主 locale 初始化（pgserver 继承环境），因此这里断言
「encoding=UTF8 + collate 与 ctype 一致 + 大小写敏感」这一**不变语义**，而非绑定
单一 locale 字面值；生产固定值为 ``C.UTF-8``（编排与文档固定）。
"""

from __future__ import annotations


def test_t05_encoding_and_locale_are_fixed(raw_conn):
    datcollate, datctype, encoding = raw_conn.execute(
        "SELECT datcollate, datctype, pg_encoding_to_char(encoding) "
        "FROM pg_database WHERE datname = current_database()"
    ).fetchone()

    assert encoding == "UTF8"
    assert datcollate and datctype
    # locale 固定：collate 与 ctype 一致（大小写敏感语义由下一条测试直接断言）。
    assert datcollate == datctype


def test_t05_case_sensitive_equality(raw_conn):
    (case_sensitive,) = raw_conn.execute("SELECT ('cluster-a' = 'Cluster-A')").fetchone()
    assert case_sensitive is False, "§22：大小写敏感等值比较必须成立"
