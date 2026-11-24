import { useEffect, useState } from 'react'
import { api } from '../api'

// 四面对照 + 审计重放 + 回执宣称核对：两格数字必须能由会话集合 ∪ 占用列重放。
export default function Reconcile() {
  const [rep, setRep] = useState(null)
  const [audit, setAudit] = useState([])
  const [msg, setMsg] = useState('')
  const load = () =>
    Promise.all([api.对照(), api.审计()]).then(([r, a]) => {
      setRep(r)
      setAudit(a)
    })
  useEffect(() => {
    load()
  }, [])
  const repair = async () => {
    try {
      const r = await api.重放修复()
      setMsg(r.纠正.length ? `已按会话集合纠正 ${r.纠正.length} 处` : '证据一致，无需纠正')
    } catch (e) {
      setMsg(e.message)
    }
    load()
  }
  if (!rep) return <div className="page"><p className="msg">加载中</p></div>
  const ev = rep.证据 || {}
  return (
    <div className="page">
      <h2>对账</h2>
      <p className="lead">
        口径 {rep.口径} ·{' '}
        <span className={rep.对齐 ? 'ok' : 'msg'}>{rep.对齐 ? '四面对齐' : `${rep.拧花.length} 处拧花`}</span>
      </p>
      <div className="panel">
        <h3>重放</h3>
        <div className="grid">
          <div className="stat">
            <div className="k">钉桩桩数（重放）</div>
            <div className="v">{rep.重放.钉桩桩数}</div>
          </div>
          <div className="stat">
            <div className="k">充电中会话数（重放）</div>
            <div className="v">{rep.重放.充电中会话数}</div>
          </div>
          <div className="stat">
            <div className="k">最新审计双计数</div>
            <div className={`v ${rep.审计.重放一致 ? 'ok' : ''}`}>
              {rep.审计.最新双计数 ? `${rep.审计.最新双计数.钉桩桩数}/${rep.审计.最新双计数.充电中会话数}` : '无'}
            </div>
          </div>
        </div>
        <p className="msg">
          会话钉桩 [{ev['充电中/结算中钉桩']?.join(', ') || '无'}] · 桩位占用列 [
          {ev.桩位占用列?.join(', ') || '无'}] · 会话钉枪 [{ev['充电中/结算中钉枪']?.join(', ') || '无'}] ·
          枪线占用列 [{ev['枪线占用列']?.join(', ') || '无'}]
        </p>
      </div>
      <div className="panel">
        <h3>拧花</h3>
        {rep.拧花.length === 0 ? (
          <p className="ok">无</p>
        ) : (
          <ul>
            {rep.拧花.map((v) => (
              <li key={v} className="msg">{v}</li>
            ))}
          </ul>
        )}
        {rep.回执.旁路宣称.length > 0 && (
          <p className="msg">回执/审计存在旁路对齐宣称 {rep.回执.旁路宣称.length} 处，必须重放修复作废。</p>
        )}
        <button type="button" className="primary" onClick={repair}>
          按会话集合重放修复
        </button>
        <p className="msg">{msg}</p>
      </div>
      <div className="panel">
        <h3>审计流水（只增）</h3>
        <table>
          <thead>
            <tr>
              <th>序号</th>
              <th>时间</th>
              <th>类别</th>
              <th>双计数</th>
            </tr>
          </thead>
          <tbody>
            {audit.map((a) => (
              <tr key={a.序号}>
                <td>{a.序号}</td>
                <td>{a.时间}</td>
                <td>{a.类别}</td>
                <td>
                  {a.明细?.双计数
                    ? `${a.明细.双计数.钉桩桩数}/${a.明细.双计数.充电中会话数}`
                    : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
