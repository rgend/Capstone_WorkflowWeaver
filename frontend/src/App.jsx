import { useEffect, useState } from 'react'
import Header from './components/Header'
import IntegrationStatus from './components/IntegrationStatus'
import WorkflowComposer from './components/WorkflowComposer'
import LiveLogPanel from './components/LiveLogPanel'
import ExecutionReportView from './components/ExecutionReportView'
import TemplateLibrary from './components/TemplateLibrary'
import HistoryList from './components/HistoryList'
import { getHealth, getReport, streamWorkflow } from './api'

export default function App() {
  const [activeTab, setActiveTab] = useState('compose')
  const [health, setHealth] = useState(null)
  const [prefillTemplate, setPrefillTemplate] = useState(null)

  const [activeRunId, setActiveRunId] = useState(null)
  const [events, setEvents] = useState([])
  const [report, setReport] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)

  const [historyReport, setHistoryReport] = useState(null)

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null))
  }, [])

  function handleRunStarted(runId) {
    setActiveRunId(runId)
    setEvents([])
    setReport(null)
    setIsRunning(true)

    const close = streamWorkflow(runId, {
      onLog: (event) => setEvents((prev) => [...prev, event]),
      onDone: (finalReport) => {
        setReport(finalReport)
        setIsRunning(false)
        setHistoryRefreshKey((k) => k + 1)
      },
      onError: () => setIsRunning(false),
    })
    return close
  }

  function handleUseTemplate(template) {
    setPrefillTemplate({ ...template, _ts: Date.now() })
    setActiveTab('compose')
  }

  function handleSelectHistoryRun(runId) {
    setHistoryReport(null)
    getReport(runId).then(setHistoryReport).catch(() => setHistoryReport(null))
  }

  return (
    <div className="min-h-screen">
      <Header activeTab={activeTab} onTabChange={setActiveTab} health={health} />

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {activeTab === 'compose' && (
          <>
            <section className="bg-white/[0.03] border border-white/10 rounded-xl p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-white font-semibold">New workflow</h2>
                <IntegrationStatus health={health} />
              </div>
              <WorkflowComposer
                key={prefillTemplate?._ts ?? 'default'}
                prefill={prefillTemplate}
                onRunStarted={handleRunStarted}
                disabled={isRunning}
              />
            </section>

            {activeRunId && (
              <section className="bg-white/[0.03] border border-white/10 rounded-xl p-6 space-y-5">
                <h2 className="text-white font-semibold">Live execution</h2>
                <LiveLogPanel events={events} isRunning={isRunning} />
                {report && <ExecutionReportView report={report} />}
              </section>
            )}
          </>
        )}

        {activeTab === 'templates' && (
          <section className="space-y-5">
            <h2 className="text-white font-semibold">Workflow templates</h2>
            <TemplateLibrary onUseTemplate={handleUseTemplate} />
          </section>
        )}

        {activeTab === 'history' && (
          <section className="space-y-6">
            <h2 className="text-white font-semibold">Run history</h2>
            <HistoryList onSelectRun={handleSelectHistoryRun} refreshKey={historyRefreshKey} />
            {historyReport && (
              <div className="bg-white/[0.03] border border-white/10 rounded-xl p-6">
                <ExecutionReportView report={historyReport} />
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  )
}
