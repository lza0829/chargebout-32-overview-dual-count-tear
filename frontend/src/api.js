async function req(path, opts = {}) {
  const r = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  })
  const text = await r.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = { detail: text }
  }
  if (!r.ok) {
    const msg = data?.detail || data?.消息 || text || '请求失败'
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

export const api = {
  健康: () => req('/健康'),
  总览: () => req('/总览'),
  站点: () => req('/站点'),
  桩位: (站点编号) => req(站点编号 ? `/桩位?站点编号=${站点编号}` : '/桩位'),
  枪线: (桩位编号) => req(桩位编号 ? `/枪线?桩位编号=${桩位编号}` : '/枪线'),
  费率: () => req('/费率'),
  会话: (状态) => req(状态 ? `/会话?状态=${encodeURIComponent(状态)}` : '/会话'),
  会话详情: (id) => req(`/会话/${id}`),
  开会话: (body) => req('/开会话', { method: 'POST', body: JSON.stringify(body) }),
  脉冲: (id, body) => req(`/会话/${id}/脉冲`, { method: 'POST', body: JSON.stringify(body) }),
  结算: (id) => req(`/会话/${id}/结算`, { method: 'POST', body: '{}' }),
  超时: (id) => req(`/会话/${id}/超时`, { method: 'POST', body: '{}' }),
  中断: (id, 原因 = '急停') =>
    req(`/会话/${id}/中断`, { method: 'POST', body: JSON.stringify({ 原因 }) }),
  充日: () => req('/充日'),
  封印: (备注 = '') => req('/充日/封印', { method: 'POST', body: JSON.stringify({ 备注 }) }),
  解封: () => req('/充日/解封', { method: 'POST', body: '{}' }),
  设置: () => req('/设置'),
  写设置: (body) => req('/设置', { method: 'POST', body: JSON.stringify(body) }),
  改桩态: (id, 状态) =>
    req(`/桩位/${id}/状态`, { method: 'POST', body: JSON.stringify({ 状态 }) }),
}
