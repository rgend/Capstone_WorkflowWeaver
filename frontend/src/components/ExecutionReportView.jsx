import { useState } from 'react'
import { statusMeta, TOOL_META } from '../statusMeta'

function OutputLink({ output }) {
  if (!output) return null
  const url = output.url
  const label = output.title || output.name || 'output'
  if (!url) return null
  return (
    <a href={url} target="_blank" rel="noreferrer" className="text-brand-300 hover:text-brand-200 underline text-xs">
      {label} {output.mock && <span className="text-slate-500">(mock)</span>}
    </a>
  )
}

function StepRow({ step }) {
  const meta = statusMeta(step.status)
  const tool = TOOL_META[step.tool] || TOOL_META.none
  const duration =
    step.started_at && step.finished_at ? `${((step.finished_at - step.started_at) * 1000).toFixed(0)}ms` : null

  return (
    <div className="border border-white/10 rounded-lg p-4 bg-white/[0.02]">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="text-lg leading-none mt-0.5">{tool.emoji}</span>
          <div>
            <p className="text-sm text-white font-medium">{step.description}</p>
            <p className="text-xs text-slate-500 mt-0.5">
              {tool.label} · {step.action}
              {step.attempts > 1 && ` · ${step.attempts} attempts`}
              {duration && ` · ${duration}`}
            </p>
          </div>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${meta.badge}`}>{meta.label}</span>
      </div>
      {step.error && <p className="text-xs text-red-400 mt-2 pl-8">{step.error}</p>}
      {step.output && (
        <div className="mt-2 pl-8">
          <OutputLink output={step.output} />
        </div>
      )}
    </div>
  )
}

export default function ExecutionReportView({ report }) {
  const [showJson, setShowJson] = useState(false)
  if (!report) return null
  const meta = statusMeta(report.status)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-white font-semibold">Execution report</h3>
          {report.intent_summary && <p className="text-sm text-slate-400 mt-0.5">{report.intent_summary}</p>}
        </div>
        <span className={`text-xs px-2.5 py-1 rounded-full ${meta.badge}`}>{meta.label}</span>
      </div>

      <div className="space-y-2.5">
        {report.steps.map((step) => (
          <StepRow key={step.step_id} step={step} />
        ))}
        {report.steps.length === 0 && <p className="text-sm text-slate-500">No steps were executed.</p>}
      </div>

      <div className="flex items-center gap-4 text-xs text-slate-500 pt-1">
        <span>Run ID: {report.run_id}</span>
        {report.mock_mode && <span className="text-amber-400">Dry-run mode — no live external calls were made</span>}
        {report.langfuse_trace_url && (
          <a href={report.langfuse_trace_url} target="_blank" rel="noreferrer" className="text-brand-300 underline">
            View Langfuse trace
          </a>
        )}
        <button onClick={() => setShowJson((s) => !s)} className="underline hover:text-slate-300">
          {showJson ? 'Hide' : 'View'} raw JSON
        </button>
      </div>

      {showJson && (
        <pre className="text-xs bg-black/40 border border-white/10 rounded-lg p-3 overflow-x-auto text-slate-300">
          {JSON.stringify(report, null, 2)}
        </pre>
      )}
    </div>
  )
}
