import { NavLink } from 'react-router-dom'

const nav = [
  { to: '/', label: 'Agents', icon: '⬡' },
  { to: '/events', label: 'Events', icon: '⚡' },
  { to: '/register', label: 'Register', icon: '+' },
]

export function Layout({ children }) {
  return (
    <div className="min-h-screen flex flex-col bg-[#0f1117]">
      <header className="border-b border-slate-800 bg-[#0f1117]/90 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 flex items-center justify-between h-14">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold text-white tracking-tight">
              Agent<span className="text-violet-400">Sentinel</span>
            </span>
            <span className="text-xs text-slate-500 border border-slate-700 px-1.5 py-0.5 rounded">MVP</span>
          </div>
          <nav className="flex items-center gap-1">
            {nav.map(({ to, label, icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-1.5 rounded text-sm transition-colors
                  ${isActive
                    ? 'bg-violet-500/10 text-violet-300 border border-violet-500/20'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  }`
                }
              >
                <span className="text-xs opacity-70">{icon}</span>
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        {children}
      </main>
    </div>
  )
}
