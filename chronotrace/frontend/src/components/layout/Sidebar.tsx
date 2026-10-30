import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Upload, Clock, Network, MessageSquare } from 'lucide-react';

const nav = [
  { to: '/',         label: 'Dashboard',  icon: LayoutDashboard },
  { to: '/ingest',   label: 'Ingest',     icon: Upload },
  { to: '/timeline', label: 'Timeline',   icon: Clock },
  { to: '/graph',    label: 'Graph',      icon: Network },
  { to: '/ask',      label: 'Ask AI',     icon: MessageSquare },
];

export default function Sidebar() {
  return (
    <aside className="w-56 min-h-screen bg-gray-900 text-gray-100 flex flex-col py-6 px-3 gap-1 shrink-0">
      <div className="px-3 mb-6">
        <h1 className="text-lg font-bold text-white tracking-tight">⏱ ChronoTrace</h1>
        <p className="text-xs text-gray-400 mt-0.5">Temporal Knowledge AI</p>
      </div>
      {nav.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors
            ${isActive ? 'bg-indigo-600 text-white' : 'text-gray-300 hover:bg-gray-800 hover:text-white'}`
          }
        >
          <Icon size={16} />
          {label}
        </NavLink>
      ))}
    </aside>
  );
}

