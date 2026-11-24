import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Rates() {
  const [list, setList] = useState([])
  useEffect(() => {
    api.费率().then(setList)
  }, [])
  return (
    <div className="page">
      <h2>费率</h2>
      <p className="lead">峰平谷电价档，开会话时可锁定当时档。</p>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>峰价</th>
              <th>平价</th>
              <th>谷价</th>
              <th>启用</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>{r.peak_price}</td>
                <td>{r.flat_price}</td>
                <td>{r.valley_price}</td>
                <td>{r.active ? '是' : '否'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
