import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  FileText,
  Layers,
  Clock,
  Network,
  MessageSquare,
  Search,
  Activity,
  ChevronLeft,
  ChevronRight,
  Zap,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/documents', label: 'Documents', icon: FileText },
  { path: '/features', label: 'Features', icon: Layers },
  { path: '/timeline', label: 'Timeline', icon: Clock },
  { path: '/graph', label: 'Knowledge Graph', icon: Network },
  { path: '/assistant', label: 'AI Assistant', icon: MessageSquare },
  { path: '/evidence', label: 'Evidence', icon: Search },
  { path: '/ingestion', label: 'Ingestion Monitor', icon: Activity },
]

interface LayoutProps {
  children: React.ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="flex h-screen bg-[#070b19] text-slate-100 overflow-hidden font-sans">
      {/* Sidebar */}
      <aside
        className={cn(
          'flex flex-col border-r border-purple-900/30 bg-[#0a0f24] transition-all duration-300 relative z-30 shadow-xl',
          collapsed ? 'w-16' : 'w-64'
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 py-4.5 border-b border-purple-900/30">
          <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-tr from-purple-700 to-indigo-500 flex items-center justify-center shadow-md shadow-purple-900/40">
            <Zap size={18} className="text-white" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="text-sm font-bold tracking-tight text-white flex items-center gap-1.5">
                ChronoGraph
                <span className="text-[10px] font-mono uppercase bg-purple-500/20 text-purple-300 px-1.5 py-0.2 rounded border border-purple-500/30">
                  v2.0
                </span>
              </div>
              <div className="text-[11px] text-purple-400 font-medium">Temporal Knowledge System</div>
            </div>
          )}
        </div>

        {/* Navigation list */}
        <nav className="flex-1 py-4 px-2.5 space-y-1 overflow-y-auto">
          {navItems.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all duration-200 group relative',
                  isActive
                    ? 'bg-purple-600/20 text-purple-200 border border-purple-500/40 shadow-sm shadow-purple-950/50 font-semibold'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/40 border border-transparent'
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon
                    size={17}
                    className={cn(
                      'flex-shrink-0 transition-colors',
                      isActive ? 'text-purple-400' : 'text-slate-400 group-hover:text-purple-300'
                    )}
                  />
                  {!collapsed && <span className="truncate">{label}</span>}
                  {isActive && !collapsed && (
                    <span className="ml-auto w-1.5 h-1.5 rounded-full bg-purple-400 shadow-sm shadow-purple-400" />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Bottom system status & collapse toggle */}
        <div className="p-2 border-t border-purple-900/30 bg-[#090d20]">
          {!collapsed && (
            <div className="px-2.5 py-2 mb-1 rounded-lg bg-slate-900/50 border border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
              <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                Backend Live
              </span>
              <span className="font-mono text-[10px] text-slate-500">127.0.0.1:8000</span>
            </div>
          )}
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="w-full flex items-center justify-center py-2 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-slate-800/50 transition-colors"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto bg-[#070b19]">{children}</main>
    </div>
  )
}
