"""半截装载回滚：装载批中途撞上未知站时的失败闭口。

本仓全局选定「整批回滚」口径（二选一，不混用）：

- 任一条事件撞上未知站点 → 本批所有卡已写入的刷卡点 / 开腿账 / 行程账 / 旁路匣
  一律回滚到批前状态；
- 批报告标记失败，不得报告成功却留下脏行程；
- 失败闭落一条只读记录（批次编号、肇事卡、保留行程数、回滚范围标记、valid）。

对比口径（本仓不采用）：「肇事卡隔离回滚」——仅回滚肇事卡，保留其他卡已成对行程，
批报告部分成功。若改用该口径，两口径下卡A行程是否仍在会分叉，故必须全局只贯彻一种。
"""

import json

from app.db import 连接
from app.seed import 此刻

NAME = "半截装载回滚"
架构 = "整批回滚"
回滚范围标记 = "整批"
口径 = "任一条失败则本批所有卡的刷卡/开腿/行程/旁路回滚到批前；批报告失败"

# 该批写入在四本账上的归属列，用于验「整批回滚后一条不剩」
归属表 = (
    ("刷卡点", "批次编号"),
    ("开腿账", "批次编号"),
    ("行程账", "批次编号"),
    ("旁路匣", "批次编号"),
)


class 批失败(Exception):
    """批内致命事件：事务回滚后由装载层落失败闭。"""

    def __init__(self, 肇事卡: str, 肇事事件编号: str, 失败原因: str, 报告: dict):
        super().__init__(f"{失败原因}:{肇事事件编号}")
        self.肇事卡 = 肇事卡
        self.肇事事件编号 = 肇事事件编号
        self.失败原因 = 失败原因
        self.报告 = 报告


def 架构信息() -> dict:
    return {
        "项目": "闸对",
        "主题": NAME,
        "架构": 架构,
        "回滚范围标记": 回滚范围标记,
        "口径": 口径,
        "失败触发": ["未知站点"],
        "批报告": "失败（成功=false）",
        "保留行程数": 0,
        "语义": {
            "卡A成对后卡B遇未知站": "批内卡A已成对行程随整批回滚消失；卡B不产旁路；批报告失败",
            "纯成功批": "全部成对，批报告成功",
            "并发第二批": "单写事务排队，不读半截开腿",
        },
        "端点": "/api/批失败闭/{批次编号}",
    }


def 记失败闭(conn, 批次编号: str, 肇事卡: str, 肇事事件编号: str, 报告: dict) -> None:
    """在事务内写失败闭（调用方负责 BEGIN/COMMIT）。"""
    conn.execute(
        """INSERT OR REPLACE INTO 批失败闭
           (批次编号,时刻,肇事卡,肇事事件编号,保留行程数,回滚范围,架构,valid,报告)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            批次编号,
            此刻(),
            肇事卡,
            肇事事件编号,
            int(报告.get("保留行程数", 0)),
            回滚范围标记,
            架构,
            1,
            json.dumps(报告, ensure_ascii=False),
        ),
    )


def 校valid(conn, 批次编号: str, 保留行程数: int) -> bool:
    """整批回滚口径下：该批在四本账上不得残留，保留行程数必须为 0。"""
    if int(保留行程数) != 0:
        return False
    for 表, 列 in 归属表:
        n = conn.execute(
            f"SELECT COUNT(*) FROM {表} WHERE {列}=?", (批次编号,)
        ).fetchone()[0]
        if n:
            return False
    return True


def _行转闭(row) -> dict:
    d = dict(row)
    d["valid"] = bool(d.get("valid"))
    d["回滚范围标记"] = d.get("回滚范围", 回滚范围标记)
    try:
        d["报告"] = json.loads(d.pop("报告", "{}"))
    except Exception:
        d["报告"] = {}
    return d


def 取闭(批次编号: str):
    conn = 连接()
    try:
        row = conn.execute(
            "SELECT * FROM 批失败闭 WHERE 批次编号=?", (批次编号,)
        ).fetchone()
        if not row:
            return None
        d = _行转闭(row)
        有效 = 校valid(conn, 批次编号, d["保留行程数"])
        d["valid"] = bool(d["valid"]) and 有效
        d["有效"] = d["valid"]
        d["回滚范围标记"] = d.get("回滚范围", 回滚范围标记)
        d["保留行程数"] = int(d["保留行程数"])
        return d
    finally:
        conn.close()


def 列闭() -> list:
    conn = 连接()
    try:
        return [
            _行转闭(r)
            for r in conn.execute("SELECT * FROM 批失败闭 ORDER BY 时刻 DESC, 批次编号 DESC")
        ]
    finally:
        conn.close()
