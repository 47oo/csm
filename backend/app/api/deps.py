"""请求级依赖：事务边界基座。

每个请求一个 Session；路由成功返回后提交，抛异常则回滚。这是 F012 交付的
**事务边界基座**，F014 的加锁协议建立其上。
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.db_sessionmaker
    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
