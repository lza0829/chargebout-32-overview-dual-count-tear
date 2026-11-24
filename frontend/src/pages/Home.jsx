import { useEffect, useState } from 'react'
import { api } from '../api'

// 臂 A：总览两格 = 充电中/结算中会话集合重放；显示值与证据同源，绝不读任何
// 「surface_*」旁路数字，也绝不在证据对不上时亮「已对齐」。
export default function Home() {
  const [o, setO] = useState(null)
  const [err, setErr] = useState('')
  const load = () => {
    setErr('')
    api
      .总览()
      .then(setO)
      .catch((e) => setErr(e.message))
  }
  useEffect(() => {
    load()
  }, [])
  if (!o) return <div className="page"><p className="msg">{err || '加载中'}</p></div>
  const aligned = o.已对齐 === true
  const ev = o.证据 || {}
  const items = [
    ['桩位空闲', o.桩位空闲],
    ['桩位占用', o.桩位占用],
    ['桩位故障', o.桩位故障],
    ['桩位维护', o.桩位维护],
    ['充电中', o.充电中],
    ['结算中', o.结算中],
    ['已关账', o.已关账],
    ['已超时', o.已超时],
    ['已中断', o.已中断],
    ['在充电量', o.在充电量],
    ['本日关账金额', o.本日关账金额],
  ]
  return (
    <div className="page">
      <h2>总览</h2>
      <p className="lead">
        营业日 {o.营业日} · 充日{o.充日已封印 ? '已封印' : '未封印'} · 口径 {o.双计数口径}
      </p>
      <div className="panel">
        <h3>钉桩 / 充电中双格（会话集合重放）</h3>
        <div className="grid">
          <div className="stat">
            <div className="k">钉桩桩数</div>
            <div className="v">{o.钉桩桩数}</div>
          </div>
          <div className="stat">
            <div className="k">充电中会话数</div>
            <div className="v">{o.充电中会话数}</div>
          </div>
          <div className="stat">
            <div className="k">对齐</div>
            <div className={`v ${aligned ? 'ok' : ''}`}>{aligned ? '已对齐' : '未对齐'}</div>
          </div>
        </div>
        {!aligned && (
          <>
            <p className="msg">
              证据对不上，两格不得宣称已对齐：{o.拧花?.join('；') || '未知拧花'}
            </p>
            <p className="msg">请到「对照」核对后调 /api/重放修复 按会话集合纠正占用列。</p>
          </>
        )}
        <p className="msg">
          会话册充电中 [{ev.充电中会话?.join(', ') || '无'}] · 会话钉桩 [
          {ev['充电中/结算中钉桩']?.join(', ') || '无'}] · 桩位占用列 [
          {ev.桩位占用列?.join(', ') || '无'}] · 枪线占用列 [
          {ev.枪线占用列?.join(', ') || '无'}]
        </p>
      </div>
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
