import os
import sqlite3
from pathlib import Path

数据目录 = Path(os.environ.get("数据目录", Path(__file__).resolve().parent.parent / "data"))
夹具目录 = Path(os.environ.get("夹具目录", Path(__file__).resolve().parent.parent.parent / "fixtures"))
库路径 = 数据目录 / "闸对.db"


def 连接(自动提交: bool = False) -> sqlite3.Connection:
    """打开库连接。

    自动提交=True 时关闭 sqlite3 的隐式事务，调用方须自己 BEGIN/COMMIT，
    以便装载批用 BEGIN IMMEDIATE + SAVEPOINT/ROLLBACK 做整批事务收口。
    busy_timeout 让并发第二批在写锁上排队，而不是立刻报 database is locked。
    """
    数据目录.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(库路径, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA busy_timeout = 10000")
    if 自动提交:
        c.isolation_level = None
    return c
