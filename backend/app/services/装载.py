import json

from app.db import 连接
from app.modules import 半截装载回滚 as 失败闭
from app.seed import 此刻
from app.services import 时间, 配对

# 装载失败口径（全局唯一，见 app/modules/半截装载回滚）：整批回滚。
# 任一条事件撞上未知站点即整批作废，批报告失败。


def _新报告(批次编号: str) -> dict:
    return {
        "批次编号": 批次编号,
        "成功": True,
        "结果": "成功",
        "已回滚": False,
        "失败原因": "",
        "肇事卡": "",
        "肇事事件编号": "",
        "回滚范围": 失败闭.回滚范围标记,
        "入流": 0,
        "开腿": 0,
        "成对": 0,
        "旁路": 0,
        "超时旁路": 0,
        "保留行程数": 0,
        "明细": [],
    }


def 装一批(体: dict) -> dict:
    """装载刷卡点：同卡进站开腿、出站成对；缺腿超时/孤儿旁路。

    口径：
    - 进站：同卡若已有在途开腿 → 旧腿旁路(重复进站)并开新腿
    - 出站：匹配同卡在途开腿 → 写行程账；无开腿 → 出站孤儿旁路
    - 批次末：按本批最大事件时扫缺腿超时
    - 中途撞上未知站：按「整批回滚」收口，本批四本账全部回滚，批报告失败

    事务：BEGIN IMMEDIATE 取写锁，整批写入包在一个 SAVEPOINT 里。失败时
    ROLLBACK TO SAVEPOINT，再于同一事务内落失败闭与失败批报告后提交。
    并发第二批会被写锁挡住，不会读到半截开腿。
    """
    批次编号 = 体.get("批次编号") or f"批-{此刻().replace(':', '').replace('-', '')}"
    事件列表 = 体.get("事件") or []
    conn = 连接(自动提交=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        报告 = _新报告(批次编号)
        站 = {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 站规")}
        最大行程秒 = int(站.get("最大行程秒", "7200"))
        水位 = None

        conn.execute("SAVEPOINT 本批")
        try:
            for ev in 事件列表:
                事件编号 = ev["事件编号"]
                卡号 = ev["卡号"]
                站点键 = ev["站点键"]
                方向 = ev["方向"]
                事件时 = ev["事件时"]
                处理时 = ev.get("处理时") or 此刻()

                if 水位 is None or 时间.解析(事件时) > 时间.解析(水位):
                    水位 = 事件时

                if conn.execute(
                    "SELECT 1 FROM 刷卡点 WHERE 事件编号=?", (事件编号,)
                ).fetchone():
                    报告["明细"].append({"事件编号": 事件编号, "命运": "幂等跳过"})
                    continue

                站行 = conn.execute(
                    "SELECT * FROM 站点 WHERE 站点键=?", (站点键,)
                ).fetchone()
                if not 站行:
                    报告["明细"].append(
                        {"事件编号": 事件编号, "命运": "批失败-未知站", "站点键": 站点键}
                    )
                    raise 失败闭.批失败(卡号, 事件编号, "未知站点", 报告)

                if 方向 not in ("进站", "出站"):
                    conn.execute(
                        "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻, 批次编号) VALUES (?,?,?,?,?,?)",
                        (
                            "方向非法",
                            卡号,
                            事件编号,
                            json.dumps(ev, ensure_ascii=False),
                            处理时,
                            批次编号,
                        ),
                    )
                    conn.execute(
                        """INSERT INTO 刷卡点(事件编号,卡号,站点键,方向,事件时,处理时,命运,行程键,批次编号)
                           VALUES (?,?,?,?,?,?, '已旁路', '', ?)""",
                        (事件编号, 卡号, 站点键, 方向, 事件时, 处理时, 批次编号),
                    )
                    报告["旁路"] += 1
                    报告["入流"] += 1
                    报告["明细"].append({"事件编号": 事件编号, "命运": "旁路-方向非法"})
                    continue

                conn.execute(
                    """INSERT INTO 刷卡点(事件编号,卡号,站点键,方向,事件时,处理时,命运,行程键,批次编号)
                       VALUES (?,?,?,?,?,?, '已入流', '', ?)""",
                    (事件编号, 卡号, 站点键, 方向, 事件时, 处理时, 批次编号),
                )
                报告["入流"] += 1

                if 方向 == "进站":
                    旧 = conn.execute(
                        "SELECT * FROM 开腿账 WHERE 卡号=? AND 状态='在途'", (卡号,)
                    ).fetchone()
                    if 旧:
                        conn.execute(
                            "UPDATE 开腿账 SET 状态='已旁路', 更新处理时=?, 批次编号=? WHERE 开腿键=?",
                            (处理时, 批次编号, 旧["开腿键"]),
                        )
                        conn.execute(
                            "UPDATE 刷卡点 SET 命运=?, 批次编号=? WHERE 事件编号=?",
                            ("已旁路", 批次编号, 旧["进站事件编号"]),
                        )
                        conn.execute(
                            "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻, 批次编号) VALUES (?,?,?,?,?,?)",
                            (
                                "重复进站",
                                卡号,
                                旧["进站事件编号"],
                                json.dumps(
                                    {"旧开腿": 旧["开腿键"], "新进站": 事件编号},
                                    ensure_ascii=False,
                                ),
                                处理时,
                                批次编号,
                            ),
                        )
                        报告["旁路"] += 1
                        报告["明细"].append(
                            {"事件编号": 旧["进站事件编号"], "命运": "旁路-重复进站"}
                        )

                    开腿键 = f"腿-{事件编号}"
                    conn.execute(
                        """INSERT INTO 开腿账(开腿键,卡号,进站事件编号,进站站点键,进站事件时,状态,更新处理时,批次编号)
                           VALUES (?,?,?,?,?,'在途',?,?)""",
                        (开腿键, 卡号, 事件编号, 站点键, 事件时, 处理时, 批次编号),
                    )
                    conn.execute(
                        "UPDATE 刷卡点 SET 命运=? WHERE 事件编号=?",
                        ("已开腿", 事件编号),
                    )
                    报告["开腿"] += 1
                    报告["明细"].append(
                        {"事件编号": 事件编号, "命运": "已开腿", "开腿键": 开腿键}
                    )
                else:
                    开腿 = conn.execute(
                        "SELECT * FROM 开腿账 WHERE 卡号=? AND 状态='在途' ORDER BY 进站事件时 ASC LIMIT 1",
                        (卡号,),
                    ).fetchone()
                    if not 开腿:
                        conn.execute(
                            "UPDATE 刷卡点 SET 命运=? WHERE 事件编号=?",
                            ("已旁路", 事件编号),
                        )
                        conn.execute(
                            "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻, 批次编号) VALUES (?,?,?,?,?,?)",
                            (
                                "出站孤儿",
                                卡号,
                                事件编号,
                                json.dumps(ev, ensure_ascii=False),
                                处理时,
                                批次编号,
                            ),
                        )
                        报告["旁路"] += 1
                        报告["明细"].append(
                            {"事件编号": 事件编号, "命运": "旁路-出站孤儿"}
                        )
                        continue

                    行程键 = 配对.成对写出站(
                        conn, 开腿, 事件编号, 站点键, 事件时, 处理时, 批次编号
                    )
                    报告["成对"] += 1
                    报告["明细"].append(
                        {"事件编号": 事件编号, "命运": "已成对", "行程键": 行程键}
                    )

            if 水位:
                报告["超时旁路"] = 配对.扫缺腿超时(
                    conn, 最大行程秒, 水位, 此刻(), 批次编号
                )
                报告["旁路"] += 报告["超时旁路"]

            conn.execute("RELEASE 本批")
            报告["保留行程数"] = 报告["成对"]
            # 同编号重跑成功：撤掉此前失败尝试留下的失败闭，避免脏闭口。
            conn.execute("DELETE FROM 批失败闭 WHERE 批次编号=?", (批次编号,))
            conn.execute(
                "INSERT OR REPLACE INTO 装载批次(编号, 时刻, 报告) VALUES (?,?,?)",
                (批次编号, 此刻(), json.dumps(报告, ensure_ascii=False)),
            )
            conn.execute("COMMIT")
            return 报告

        except 失败闭.批失败 as e:
            尝试 = {
                "入流": 报告["入流"],
                "开腿": 报告["开腿"],
                "成对": 报告["成对"],
                "旁路": 报告["旁路"],
                "超时旁路": 报告["超时旁路"],
            }
            conn.execute("ROLLBACK TO 本批")
            conn.execute("RELEASE 本批")

            # 仍在同一写事务内清点回滚结果，锁不释放给并发第二批。
            保留行程数 = conn.execute(
                "SELECT COUNT(*) FROM 行程账 WHERE 批次编号=?", (批次编号,)
            ).fetchone()[0]
            保留开腿数 = conn.execute(
                "SELECT COUNT(*) FROM 开腿账 WHERE 批次编号=? AND 状态='在途'",
                (批次编号,),
            ).fetchone()[0]
            保留旁路数 = conn.execute(
                "SELECT COUNT(*) FROM 旁路匣 WHERE 批次编号=?", (批次编号,)
            ).fetchone()[0]
            残留刷卡数 = conn.execute(
                "SELECT COUNT(*) FROM 刷卡点 WHERE 批次编号=?", (批次编号,)
            ).fetchone()[0]

            报告.update(
                {
                    "成功": False,
                    "结果": "失败",
                    "已回滚": True,
                    "失败原因": e.失败原因,
                    "肇事卡": e.肇事卡,
                    "肇事事件编号": e.肇事事件编号,
                    "回滚范围": 失败闭.回滚范围标记,
                    # 批报告与库态同票：主计数一律为回滚后的已提交值
                    "入流": 0,
                    "开腿": 0,
                    "成对": 0,
                    "旁路": 0,
                    "超时旁路": 0,
                    "保留行程数": 保留行程数,
                    "保留开腿数": 保留开腿数,
                    "保留旁路数": 保留旁路数,
                    "残留刷卡数": 残留刷卡数,
                    "尝试": 尝试,
                }
            )
            报告["valid"] = (
                保留行程数 == 0
                and 保留开腿数 == 0
                and 保留旁路数 == 0
                and 残留刷卡数 == 0
            )

            失败闭.记失败闭(
                conn, 批次编号, e.肇事卡, e.肇事事件编号, 报告
            )
            conn.execute(
                "INSERT OR REPLACE INTO 装载批次(编号, 时刻, 报告) VALUES (?,?,?)",
                (批次编号, 此刻(), json.dumps(报告, ensure_ascii=False)),
            )
            conn.execute("COMMIT")
            return 报告

    except BaseException:
        try:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()
