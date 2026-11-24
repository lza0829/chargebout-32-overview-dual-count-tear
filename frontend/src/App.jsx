import { NavLink, Route, Routes } from 'react-router-dom'
import Home from './pages/Home'
import Sites from './pages/Sites'
import Piles from './pages/Piles'
import Guns from './pages/Guns'
import Rates from './pages/Rates'
import OpenSession from './pages/OpenSession'
import Sessions from './pages/Sessions'
import Pulses from './pages/Pulses'
import Settle from './pages/Settle'
import Timeout from './pages/Timeout'
import DaySeal from './pages/DaySeal'
import Settings from './pages/Settings'

const links = [
  ['/', '总览'],
  ['/开会话', '开会话'],
  ['/脉冲', '记脉冲'],
  ['/结算', '结算关账'],
  ['/超时', '超时中断'],
  ['/会话', '会话册'],
  ['/桩位', '桩位'],
  ['/枪线', '枪线'],
  ['/站点', '站点'],
  ['/费率', '费率'],
  ['/充日', '充日封印'],
  ['/设置', '设置'],
]

export default function App() {
  return (
    <div className="shell">
      <header className="top">
        <div className="brand-block">
          <p className="eyebrow">路边与场站充电</p>
          <h1 className="brand">充桩条</h1>
        </div>
        <nav className="nav">
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'on' : '')}>
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/开会话" element={<OpenSession />} />
          <Route path="/脉冲" element={<Pulses />} />
          <Route path="/结算" element={<Settle />} />
          <Route path="/超时" element={<Timeout />} />
          <Route path="/会话" element={<Sessions />} />
          <Route path="/桩位" element={<Piles />} />
          <Route path="/枪线" element={<Guns />} />
          <Route path="/站点" element={<Sites />} />
          <Route path="/费率" element={<Rates />} />
          <Route path="/充日" element={<DaySeal />} />
          <Route path="/设置" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
