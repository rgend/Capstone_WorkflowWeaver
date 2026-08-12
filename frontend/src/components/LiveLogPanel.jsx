import { useEffect, useRef } from 'react'
import { statusMeta } from '../statusMeta'

function formatTime(ts) {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleTimeString([], { hour12: false })
}

export default function LiveLogPanel({ events, isRunning }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [events])

  if (events.length === 0) {
    return (
      <div className="text-sm text-slate-500 py-10 text-center border border-dashed border-white/10 rounded-lg">
        Execution logs will stream here in real time once you run a workflow.
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-white/10 bg-black/30 max-h-[420px] overflow-y-auto p-3 space-y-1.5 font-mono text-[13px]">
      {events.map((ev) => {
        const meta = statusMeta(ev.status)
        return (
          <div key={ev.seq} className="flex items-start gap-2.5 py-1">
            <span className="text-slate-500 shrink-0 pt-0.5">{formatTime(ev.timestamp)}</span>
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 mt-1.5 ${meta.dot}`} />
            <span className="text-slate-400 shrink-0">[{ev.node}]</span>
            <span className={meta.text}>{ev.message}</span>
          </div>
        )
      })}
      {isRunning && (
        <div className="flex items-center gap-2 text-slate-500 pt-1">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
          agent working...
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
