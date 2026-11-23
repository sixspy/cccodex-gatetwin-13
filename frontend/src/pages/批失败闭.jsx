import React, { useEffect, useState } from "react";
import { 取 } from "../api.js";

export default function 批失败闭() {
  const [口径, 设口径] = useState(null);
  const [行, 设行] = useState([]);
  const [错, 设错] = useState("");
  const 刷 = async () => {
    设错("");
    try {
      const [k, l] = await Promise.all([取("/装载口径"), 取("/批失败闭")]);
      设口径(k);
      设行(l);
    } catch (e) {
      设错(String(e.message || e));
    }
  };
  useEffect(() => { 刷(); }, []);
  return (
    <div>
      <h1 className="题">批失败闭</h1>
      <p className="述">
        装载批中途撞上未知站时的失败闭口。只读：批次编号、肇事卡、保留行程数、回滚范围标记、valid。
      </p>
      {口径 && (
        <div className="提示条">
          当前架构：<b>{口径.架构}</b> —— {口径.口径}。
          语义：卡A成对后卡B遇未知站 → {口径.语义["卡A成对后卡B遇未知站"]}。
        </div>
      )}
      <div className="行">
        <button className="次" onClick={刷}>刷新</button>
      </div>
      {错 && <p className="讯">{错}</p>}
      {!行.length ? (
        <div className="空态">尚无批失败闭。去「刷卡流」灌「半截装载回滚样例」制造一次失败批。</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>批次编号</th><th>时刻</th><th>肇事卡</th><th>肇事事件</th>
              <th>保留行程数</th><th>回滚范围</th><th>valid</th>
            </tr>
          </thead>
          <tbody>
            {行.map((r) => (
              <tr key={r.批次编号}>
                <td>{r.批次编号}</td><td>{r.时刻}</td><td>{r.肇事卡}</td>
                <td>{r.肇事事件编号}</td><td>{r.保留行程数}</td>
                <td>{r.回滚范围标记 || r.回滚范围}</td>
                <td><span className={`徽章 ${r.valid ? "通" : "败"}`}>{r.valid ? "valid" : "invalid"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
