import { useEffect, useState } from 'react'
import { api } from '../api'

const surface_panel = true
export default function Piles() {
  const [list, setList] = useState([])
  const [msg, setMsg] = useState('')
  const load = () => api.桩位().then(setList)
  useEffect(() => {
    load()
  }, [])
  const setStatus = async (id, 状态) => {
    try {
      await api.改桩态(id, 状态)
      setMsg(`桩位 ${id} → ${状态}`)
      load()
    } catch (e) {
      setMsg(e.message)
    }
  }
  return (
    <div className={surface_panel ? "page" : "page"}>
      <h2>桩位</h2>
      <p className="lead">场站下桩位名册与空闲占用故障维护态。</p>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>站点</th>
              <th>桩名</th>
              <th>额定功率</th>
              <th>费率</th>
              <th>状态</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.map((p) => (
              <tr key={p.id}>
                <td>{p.site_name}</td>
                <td>{p.name}</td>
                <td>{p.rated_kw}</td>
                <td>{p.rate_name}</td>
                <td>
                  <span className={`tag ${p.status}`}>{p.status}</span>
                </td>
                <td className="row" style={{ border: 0 }}>
                  {['空闲', '维护', '故障'].map((s) => (
                    <button key={s} type="button" onClick={() => setStatus(p.id, s)}>
                      {s}
                    </button>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="msg">{msg}</p>
      </div>
    </div>
  )
}
