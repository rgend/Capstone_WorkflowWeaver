import { useEffect, useState } from 'react'
import { getTemplates } from '../api'

const ICONS = {
  'clipboard-list': '\u{1F4CB}',
  calendar: '\u{1F4C5}',
  'alert-triangle': '\u{26A0}\u{FE0F}',
  'file-text': '\u{1F4C4}',
}

export default function TemplateLibrary({ onUseTemplate }) {
  const [templates, setTemplates] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    getTemplates().then(setTemplates).catch((err) => setError(err.message))
  }, [])

  if (error) return <p className="text-sm text-red-400">{error}</p>

  return (
    <div className="grid sm:grid-cols-2 gap-4">
      {templates.map((t) => (
        <div key={t.id} className="border border-white/10 rounded-xl p-5 bg-white/[0.02] flex flex-col">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xl">{ICONS[t.icon] || '\u{2699}\u{FE0F}'}</span>
            <span className="text-xs uppercase tracking-wide text-slate-500">{t.category}</span>
          </div>
          <h3 className="text-white font-semibold">{t.name}</h3>
          <p className="text-sm text-slate-400 mt-1.5 flex-1">{t.description}</p>
          <button
            onClick={() => onUseTemplate(t)}
            className="mt-4 self-start text-sm px-3.5 py-1.5 rounded-lg bg-brand-500/15 text-brand-300 hover:bg-brand-500/25 transition-colors"
          >
            Use this template
          </button>
        </div>
      ))}
      {templates.length === 0 && !error && <p className="text-sm text-slate-500">Loading templates...</p>}
    </div>
  )
}
