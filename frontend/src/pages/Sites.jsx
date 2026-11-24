import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Sites() {
  const [list, setList] = useState([])
  useEffect(() => {
    api.站点().then(setList)
  }, [])
  return (
    <div className="page">
      <h2>站点</h2>
      <p className="lead">路边站与场站名册。</p>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>地址</th>
              <th>启用</th>
            </tr>
          </thead>
          <tbody>
            {list.map((s) => (
              <tr key={s.id}>
                <td>{s.name}</td>
                <td>{s.address}</td>
                <td>{s.active ? '是' : '否'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
