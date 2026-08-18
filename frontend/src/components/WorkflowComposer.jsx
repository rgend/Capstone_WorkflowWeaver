import { useState } from 'react'
import { startWorkflow } from '../api'

// Parent remounts this component (via `key`) whenever a new template is
// picked, so prefill only needs to seed initial state — no effect needed.
export default function WorkflowComposer({ prefill, onRunStarted, disabled }) {
  const [description, setDescription] = useState(prefill?.nl_description || '')
  const [meetingNotes, setMeetingNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [templateId, setTemplateId] = useState(prefill?.id ?? null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!description.trim()) {
      setError('Describe the workflow you want executed.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const { run_id } = await startWorkflow({
        description,
        meeting_notes: meetingNotes.trim() || null,
        template_id: templateId,
      })
      onRunStarted(run_id, { description, meeting_notes: meetingNotes })
      setSubmitting(false)
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className="block text-sm font-medium text-slate-200 mb-1.5">
          Describe the workflow in plain English
        </label>
        <textarea
          value={description}
          onChange={(e) => {
            setDescription(e.target.value)
            setTemplateId(null)
          }}
          rows={4}
          placeholder="e.g. Take today's meeting notes and create a Notion project page, generate action items, and post a summary to Slack."
          className="w-full rounded-lg bg-white/5 border border-white/10 focus:border-brand-400 focus:ring-1 focus:ring-brand-400 outline-none px-3.5 py-3 text-sm text-white placeholder:text-slate-500 resize-none"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-200 mb-1.5">
          Meeting notes / requirements (optional)
        </label>
        <textarea
          value={meetingNotes}
          onChange={(e) => setMeetingNotes(e.target.value)}
          rows={5}
          placeholder={'Paste raw meeting notes or a requirements list here, e.g.\n- Discuss Q3 roadmap\n- Assign API redesign to backend team'}
          className="w-full rounded-lg bg-white/5 border border-white/10 focus:border-brand-400 focus:ring-1 focus:ring-brand-400 outline-none px-3.5 py-3 text-sm text-white placeholder:text-slate-500 font-mono resize-none"
        />
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={submitting || disabled}
        className="w-full sm:w-auto px-5 py-2.5 rounded-lg bg-brand-500 hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
      >
        {submitting ? 'Starting agent...' : 'Run workflow'}
      </button>
    </form>
  )
}
