import { useEffect, useState } from 'react'
import { getHistory } from '../api'
import { statusMeta } from '../statusMeta'

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleString()
}

export default function HistoryList({ onSelectRun, refreshKey }) {
  const [runs, setRuns] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    getHistory().then(setRuns).catch((err) => setError(err.message))
  }, [refreshKey])

  if (error) return <p className="text-sm text-red-400">{error}</p>
  if (runs.length === 0) return <p className="text-sm text-slate-500">No workflow runs yet. Start one from "New Workflow".</p>

  return (
    <div className="space-y-2">
      {runs.map((run) => {
        const meta = statusMeta(run.status)
        return (
          <button
            key={run.run_id}
            onClick={() => onSelectRun(run.run_id)}
            className="w-full text-left border border-white/10 rounded-lg p-4 bg-white/[0.02] hover:bg-white/[0.05] transition-colors flex items-center justify-between gap-4"
          >
            <div className="min-w-0">
              <p className="text-sm text-white truncate">{run.description}</p>
              <p className="text-xs text-slate-500 mt-0.5">{formatDate(run.started_at)} · {run.run_id}</p>
            </div>
            <span className={`text-xs px-2.5 py-1 rounded-full shrink-0 ${meta.badge}`}>{meta.label}</span>
          </button>
        )
      })}
    </div>
  )
}
