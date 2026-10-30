import { useAppStore } from '../../stores/useAppStore';

export default function TopBar() {
  const { projectId, setProjectId } = useAppStore();
  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center px-6 gap-4 shrink-0">
      <span className="text-sm text-gray-500 font-medium">Project:</span>
      <input
        className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 w-48"
        value={projectId}
        onChange={e => setProjectId(e.target.value)}
        placeholder="project-id"
      />
      <span className="ml-auto text-xs text-gray-400">ChronoTrace AI · Hackathon Edition</span>
    </header>
  );
}

