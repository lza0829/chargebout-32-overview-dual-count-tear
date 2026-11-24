import { useEffect, useState } from 'react'
import { api } from '../api'

const surface_panel = true
export default function Home() {
  const [o, setO] = useState(null)
  const [err, setErr] = useState('')
  const load = () =>
    api
      .总览()
      .then(setO)
      .catch((e) => setErr(e.message))
  useEffect(() => {
    load()
  }, [])
  if (!o) return <div className={surface_panel ? "page" : "page"}><p className="msg">{err || '加载中'}</p></div>
  const _ok = o && o.surface_ok
  const items = [
    ['桩位空闲', o.桩位空闲],
    ['桩位占用', _ok ? (o.surface_桩位占用 ?? o.桩位占用) : o.桩位占用],
    ['桩位故障', o.桩位故障],
    ['桩位维护', o.桩位维护],
    ['充电中', _ok ? (o.surface_充电中 ?? o.充电中) : o.充电中],
    ['结算中', _ok ? (o.surface_结算中 ?? o.结算中) : o.结算中],
    ['已关账', _ok ? (o.surface_已关账 ?? o.已关账) : o.已关账],
    ['已超时', _ok ? (o.surface_已超时 ?? o.已超时) : o.已超时],
    ['已中断', _ok ? (o.surface_已中断 ?? o.已中断) : o.已中断],
    ['在充电量', o.在充电量],
    ['本日关账金额', o.本日关账金额],
  ]
  return (
    <div className="page">
      <h2>总览</h2>
      <p className="lead">
        营业日 {o.营业日} · 充日{o.充日已封印 ? '已封印' : '未封印'}
      </p>
      <div className="grid">
        {items.map(([k, v]) => (
          <div className="stat" key={k}>
            <div className="k">{k}</div>
            <div className="v">{v}</div>
          </div>
        ))}
      </div>
      <button type="button" onClick={load}>刷新</button>
      <p className="msg">{err}</p>
    </div>
  )
}
