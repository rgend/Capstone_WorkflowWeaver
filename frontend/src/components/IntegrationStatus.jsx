const LABELS = {
  llm: 'LLM',
  notion: 'Notion',
  google_drive: 'Google Drive',
  slack: 'Slack',
  langfuse: 'Langfuse',
}

export default function IntegrationStatus({ health }) {
  if (!health) return null
  const entries = Object.entries(health.integrations || {})

  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([key, info]) => (
        <span
          key={key}
          title={info.configured ? 'Configured — live calls enabled' : 'Not configured — running in mock mode'}
          className={`text-xs px-2.5 py-1 rounded-full border flex items-center gap-1.5 ${
            info.configured
              ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'
              : 'border-slate-600 text-slate-400 bg-white/5'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${info.configured ? 'bg-emerald-400' : 'bg-slate-500'}`} />
          {LABELS[key] || key}
        </span>
      ))}
    </div>
  )
}
