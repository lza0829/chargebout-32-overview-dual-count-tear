import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Settings() {
  const [list, setList] = useState([])
  const [key, setKey] = useState('超时分钟')
  const [val, setVal] = useState('120')
  const [msg, setMsg] = useState('')
  const load = () => api.设置().then(setList)
  useEffect(() => {
    load()
  }, [])
  const save = async () => {
    try {
      await api.写设置({ 键: key, 值: val })
      setMsg('已保存')
      load()
    } catch (e) {
      setMsg(e.message)
    }
  }
  return (
    <div className="page">
      <h2>设置</h2>
      <p className="lead">超时分钟、脉冲默认电量等键值。</p>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>键</th>
              <th>值</th>
            </tr>
          </thead>
          <tbody>
            {list.map((s) => (
              <tr key={s.键}>
                <td>{s.键}</td>
                <td>{s.值}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row">
          <input value={key} onChange={(e) => setKey(e.target.value)} />
          <input value={val} onChange={(e) => setVal(e.target.value)} />
          <button type="button" className="primary" onClick={save}>
            保存
          </button>
        </div>
        <p className="msg">{msg}</p>
      </div>
    </div>
  )
}
