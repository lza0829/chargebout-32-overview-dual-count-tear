import { useEffect, useState } from 'react'
import { api } from '../api'

// 桩位占用列只是会话集合投影：页面对照「首页两格 / 会话册 / 占用列」，
// 对不上时如实标红，不提供任何手工「置占用」入口（臂 A）。
export default function Piles() {
  const [list, setList] = useState([])
  const [rep, setRep] = useState(null)
  const [msg, setMsg] = useState('')
  const load = () =>
    Promise.all([api.桩位(), api.对照()]).then(([ls, r]) => {
      setList(ls)
      setRep(r)
    })
  useEffect(() => {
    load()
  }, [])
  const setStatus = async (id, 状态) => {
    try {
      await api.改桩态(id, 状态)
      setMsg(`桩位 ${id} → ${状态}`)
    } catch (e) {
      setMsg(e.message)
    }
    load()
  }
  const repair = async () => {
    try {
      const r = await api.重放修复()
      setMsg(r.纠正.length ? `已按会话集合纠正 ${r.纠正.length} 处` : '证据一致，无需纠正')
    } catch (e) {
      setMsg(e.message)
    }
    load()
  }
  const aligned = rep?.对齐 === true
  return (
    <div className="page">
      <h2>桩位</h2>
      <p className="lead">
        占用列 = 充电中/结算中会话集合投影；手工置占用不开放。当前{' '}
        <span className={aligned ? 'ok' : 'msg'}>{aligned ? '四面对齐' : '四面对照拧花'}</span>
      </p>
      {!aligned && rep && (
        <div className="panel">
          <h3>拧花</h3>
          <ul>
            {rep.拧花.map((v) => (
              <li key={v} className="msg">{v}</li>
            ))}
          </ul>
          <button type="button" className="primary" onClick={repair}>
            按会话集合重放修复
          </button>
        </div>
      )}
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>站点</th>
              <th>桩名</th>
              <th>额定功率</th>
              <th>费率</th>
              <th>状态</th>
              <th>会话钉桩</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.map((p) => {
              const pinned = (rep?.会话册?.钉桩桩位 || []).includes(p.id)
              const torn = (p.status === '占用') !== pinned
              return (
                <tr key={p.id}>
                  <td>{p.site_name}</td>
                  <td>{p.name}</td>
                  <td>{p.rated_kw}</td>
                  <td>{p.rate_name}</td>
                  <td>
                    <span className={`tag ${p.status}`}>{p.status}</span>
                  </td>
                  <td className={torn ? 'msg' : ''}>{pinned ? '钉桩中' : '未钉桩'}</td>
                  <td className="row" style={{ border: 0 }}>
                    {['空闲', '维护', '故障'].map((s) => (
                      <button key={s} type="button" onClick={() => setStatus(p.id, s)}>
                        {s}
                      </button>
                    ))}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="msg">{msg}</p>
      </div>
    </div>
  )
}
