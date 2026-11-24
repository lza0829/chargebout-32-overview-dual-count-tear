import { useEffect, useState } from 'react'
import { api } from '../api'

export default function OpenSession() {
  const [piles, setPiles] = useState([])
  const [guns, setGuns] = useState([])
  const [pileId, setPileId] = useState('')
  const [gunId, setGunId] = useState('')
  const [msg, setMsg] = useState('')
  useEffect(() => {
    api.桩位().then((list) => {
      setPiles(list)
      const idle = list.find((p) => p.status === '空闲')
      if (idle) setPileId(String(idle.id))
    })
  }, [])
  useEffect(() => {
    if (!pileId) return
    api.枪线(Number(pileId)).then((list) => {
      setGuns(list)
      const ok = list.find((g) => g.status === '可用')
      setGunId(ok ? String(ok.id) : '')
    })
  }, [pileId])
  const submit = async () => {
    setMsg('')
    try {
      const body = { 桩位编号: Number(pileId) }
      if (gunId) body.枪线编号 = Number(gunId)
      const r = await api.开会话(body)
      setMsg(`已开 ${r.会话号}，锁定电价 ${r.锁定电价}`)
      const list = await api.桩位()
      setPiles(list)
    } catch (e) {
      setMsg(e.message)
    }
  }
  return (
    <div className="page">
      <h2>开会话</h2>
      <p className="lead">选空闲桩与可用枪，开出一笔充电会话并占住桩位。</p>
      <div className="panel">
        <div className="row">
          <label>桩位</label>
          <select value={pileId} onChange={(e) => setPileId(e.target.value)}>
            {piles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.site_name} · {p.name} · {p.status}
              </option>
            ))}
          </select>
          <label>枪线</label>
          <select value={gunId} onChange={(e) => setGunId(e.target.value)}>
            <option value="">自动选可用</option>
            {guns.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name} · {g.status}
              </option>
            ))}
          </select>
          <button type="button" className="primary" onClick={submit}>
            发起开充
          </button>
        </div>
        <p className={`msg ${msg.startsWith('已开') ? 'ok' : ''}`}>{msg}</p>
      </div>
    </div>
  )
}
