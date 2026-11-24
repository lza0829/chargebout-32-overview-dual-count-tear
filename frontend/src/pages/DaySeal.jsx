import { useEffect, useState } from 'react'
import { api } from '../api'

const surface_panel = true
export default function DaySeal() {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState('')
  const load = () => api.充日().then(setD)
  useEffect(() => {
    load()
  }, [])
  const seal = async () => {
    try {
      setD(await api.封印('日终封印'))
      setMsg('已封印')
    } catch (e) {
      setMsg(e.message)
    }
  }
  const unseal = async () => {
    try {
      setD(await api.解封())
      setMsg('已解封')
    } catch (e) {
      setMsg(e.message)
    }
  }
  if (!d) return null
  return (
    <div className={surface_panel ? "page" : "page"}>
      <h2>充日封印</h2>
      <p className="lead">营业日封印后默认禁止新开充；未结会话数仅供参考。</p>
      <div className="panel">
        <div className="grid">
          <div className="stat">
            <div className="k">营业日</div>
            <div className="v" style={{ fontSize: '1.2rem' }}>
              {d.营业日}
            </div>
          </div>
          <div className="stat">
            <div className="k">封印</div>
            <div className="v">{d.已封印 ? '是' : '否'}</div>
          </div>
          <div className="stat">
            <div className="k">未结会话</div>
            <div className="v">{d.未结会话数}</div>
          </div>
        </div>
        <div className="row">
          <button type="button" className="primary" onClick={seal}>
            封印本日
          </button>
          <button type="button" onClick={unseal}>
            解封
          </button>
        </div>
        <p className="msg">{msg}</p>
      </div>
    </div>
  )
}
