import { useEffect, useState } from 'react'

interface HealthResponse {
  status: string
  database: string
}

type HealthState =
  | { kind: 'loading' }
  | { kind: 'done'; data: HealthResponse }
  | { kind: 'error'; message: string }

function App() {
  const [state, setState] = useState<HealthState>({ kind: 'loading' })

  useEffect(() => {
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<HealthResponse>
      })
      .then((data) => setState({ kind: 'done', data }))
      .catch((err: unknown) =>
        setState({
          kind: 'error',
          message: err instanceof Error ? err.message : 'Unknown error',
        }),
      )
  }, [])

  return (
    <main className="min-h-screen flex items-center justify-center bg-slate-100">
      <div className="bg-white rounded-xl shadow p-8 w-96">
        <h1 className="text-2xl font-bold text-slate-800 mb-1">AdaptIQ</h1>
        <p className="text-sm text-slate-500 mb-6">System health check</p>

        {state.kind === 'loading' && <p>Checking...</p>}

        {state.kind === 'error' && (
          <p className="text-red-600">Backend: unreachable ({state.message})</p>
        )}

        {state.kind === 'done' && (
          <ul className="space-y-2">
            <li className={state.data.status === 'ok' ? 'text-green-600' : 'text-red-600'}>
              Backend: {state.data.status === 'ok' ? 'OK' : state.data.status}
            </li>
            <li className={state.data.database === 'ok' ? 'text-green-600' : 'text-red-600'}>
              Database: {state.data.database === 'ok' ? 'OK' : state.data.database}
            </li>
          </ul>
        )}
      </div>
    </main>
  )
}

export default App
