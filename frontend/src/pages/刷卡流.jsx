import React, { useEffect, useState } from "react";
import { 取, 递 } from "../api.js";

const 夹具 = ["成对样例", "缺腿超时样例", "出站孤儿样例", "重复进站样例"];
const 批夹具 = [
  ["半截装载回滚样例", "A成对后B未知站（应整批回滚）"],
  ["半截装载回滚样例2", "A成对后B出站未知站（应整批回滚）"],
  ["纯成功多卡样例", "纯成功批（应全成对）"],
  ["并发失败批", "并发失败批"],
  ["并发出站批", "并发出站批"],
];

export default function 刷卡流() {
  const [行, 设行] = useState([]);
  const [讯, 设讯] = useState("");
  const [批, 设批] = useState(null);
  const 刷 = () => 取("/刷卡点").then(设行);
  useEffect(() => { 刷(); }, []);
  const 灌 = async (名) => {
    设讯("装载中…");
    try {
      const r = await 递(`/装载/夹具?名=${encodeURIComponent(名)}`);
      设批(r);
      if (r.成功) {
        设讯(`批次 ${r.批次编号}：成功 入流${r.入流} 开腿${r.开腿} 成对${r.成对} 旁路${r.旁路}`);
      } else {
        设讯(
          `批次 ${r.批次编号}：失败（${r.失败原因}，肇事卡 ${r.肇事卡}）→ ${r.回滚范围}回滚，保留行程 ${r.保留行程数}，valid=${r.valid}`
        );
      }
      await 刷();
    } catch (e) {
      设讯(String(e.message || e));
    }
  };
  return (
    <div>
      <h1 className="题">刷卡流</h1>
      <p className="述">从夹具灌进出闸事件。看命运：已开腿 / 已成对 / 已旁路。</p>
      <div className="行">
        {夹具.map((n) => (
          <button key={n} className="次 亮片" onClick={() => 灌(n)}>{n}</button>
        ))}
        <button className="次" onClick={刷}>刷新</button>
      </div>
      <div className="行">
        {批夹具.map(([n, 说]) => (
          <button key={n} className="次" title={说} onClick={() => 灌(n)}>{n}</button>
        ))}
      </div>
      {讯 && <p className="讯">{讯}</p>}
      {批 && !批.成功 && (
        <div className="提示条">
          批失败闭：批次 <b>{批.批次编号}</b> · 肇事卡 <b>{批.肇事卡}</b> · 回滚范围{" "}
          <b>{批.回滚范围}</b> · 保留行程数 <b>{批.保留行程数}</b> ·{" "}
          <span className={`徽章 ${批.valid ? "通" : "败"}`}>{批.valid ? "valid" : "invalid"}</span>
          。本批刷卡/开腿/行程/旁路已按整批回滚口径撤销。
        </div>
      )}
      {!行.length ? (
        <div className="空态">尚无刷卡点。先灌「成对样例」。</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>事件编号</th><th>卡号</th><th>站点</th><th>方向</th><th>事件时</th><th>命运</th><th>行程键</th>
            </tr>
          </thead>
          <tbody>
            {行.map((r) => (
              <tr key={r.事件编号}>
                <td>{r.事件编号}</td><td>{r.卡号}</td><td>{r.站点键}</td><td>{r.方向}</td>
                <td>{r.事件时}</td><td>{r.命运}</td><td>{r.行程键 || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
