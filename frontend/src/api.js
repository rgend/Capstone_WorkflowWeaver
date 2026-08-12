const BASE = '/api'

async function asJson(res) {
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json()
}

export function getHealth() {
  return fetch(`${BASE}/health`).then(asJson)
}

export function getTemplates() {
  return fetch(`${BASE}/templates`).then(asJson)
}

export function getHistory() {
  return fetch(`${BASE}/workflows`).then(asJson)
}

export function getReport(runId) {
  return fetch(`${BASE}/workflows/${runId}/report`).then(asJson)
}

export function startWorkflow(payload) {
  return fetch(`${BASE}/workflows`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(asJson)
}

/**
 * Opens an SSE stream for a run. Returns a close() function.
 * onLog(event) fires for each streamed step; onDone(report) fires once at the end.
 */
export function streamWorkflow(runId, { onLog, onDone, onError }) {
  const source = new EventSource(`${BASE}/workflows/${runId}/stream`)

  source.addEventListener('log', (e) => {
    try {
      onLog?.(JSON.parse(e.data))
    } catch (err) {
      onError?.(err)
    }
  })

  source.addEventListener('done', (e) => {
    try {
      onDone?.(JSON.parse(e.data))
    } catch (err) {
      onError?.(err)
    } finally {
      source.close()
    }
  })

  source.onerror = (e) => {
    onError?.(e)
  }

  return () => source.close()
}
