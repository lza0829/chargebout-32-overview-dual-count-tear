import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Guns() {
  const [list, setList] = useState([])
  useEffect(() => {
    api.枪线().then(setList)
  }, [])
  return (
    <div className="page">
      <h2>枪线</h2>
      <p className="lead">各桩枪口可用与占用态。</p>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>桩位</th>
              <th>枪名</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {list.map((g) => (
              <tr key={g.id}>
                <td>{g.pile_name}</td>
                <td>{g.name}</td>
                <td>
                  <span className={`tag ${g.status}`}>{g.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
