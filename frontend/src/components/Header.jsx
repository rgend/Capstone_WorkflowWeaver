const TABS = [
  { id: 'compose', label: 'New Workflow' },
  { id: 'templates', label: 'Templates' },
  { id: 'history', label: 'History' },
]

export default function Header({ activeTab, onTabChange, health }) {
  return (
    <header className="border-b border-white/10 bg-[#0f0f1a]/80 backdrop-blur sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between gap-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center font-bold text-white">
            W
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-white">WorkflowWeaver</h1>
            <p className="text-xs text-slate-400 -mt-0.5">Describe it. The agent runs it.</p>
          </div>
        </div>

        <nav className="flex items-center gap-1 bg-white/5 rounded-lg p-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`px-3.5 py-1.5 text-sm rounded-md transition-colors ${
                activeTab === tab.id ? 'bg-brand-500 text-white shadow' : 'text-slate-300 hover:text-white hover:bg-white/5'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-2 text-xs">
          {health ? (
            <span
              className={`px-2 py-1 rounded-full border ${
                health.mock_mode
                  ? 'border-amber-500/40 text-amber-300 bg-amber-500/10'
                  : 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'
              }`}
            >
              {health.mock_mode ? 'Dry-run mode' : 'Live mode'}
            </span>
          ) : (
            <span className="px-2 py-1 rounded-full border border-slate-600 text-slate-400">connecting...</span>
          )}
        </div>
      </div>
    </header>
  )
}
