'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

type Client = { id: string; nombre: string; codigo: string }

export default function SeleccionarCliente() {
  const router = useRouter()
  const [clients, setClients] = useState<Client[]>([])
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try { setClients(JSON.parse(localStorage.getItem('available_clients') || '[]')) }
      catch { setClients([]) }
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  async function enter() {
    if (!selected) return
    setBusy(true); setError('')
    try {
      const response = await fetch(`http://localhost:8000/auth/seleccionar-cliente?cliente_id=${encodeURIComponent(selected)}`, { method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` } })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'No se pudo seleccionar el cliente.')
      localStorage.setItem('access_token', result.access_token)
      localStorage.setItem('client_id', result.cliente_id)
      localStorage.setItem('client_name', clients.find(client => client.id === selected)?.nombre || '')
      router.replace('/dashboard')
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo seleccionar el cliente.') }
    finally { setBusy(false) }
  }

  return <main className="flex min-h-screen items-center justify-center bg-slate-50 p-5"><section className="w-full max-w-xl space-y-5 rounded-2xl border border-slate-200 bg-white p-7 shadow-sm">
    <div><h1 className="text-2xl font-bold text-brand-navy">Selecciona el cliente</h1><p className="mt-2 text-sm text-brand-muted">Tu RUC tiene acceso a más de una empresa. Elige para quién deseas consultar pedidos, facturas y pagos.</p></div>
    {clients.length === 0 ? <p role="alert" className="rounded-lg bg-amber-50 p-3 text-amber-900">No se cargaron clientes habilitados. Cierra sesión e ingresa nuevamente.</p> : <div className="space-y-2">{clients.map(client => <label key={client.id} className={`flex cursor-pointer items-center gap-3 rounded-xl border p-4 ${selected === client.id ? 'border-brand-teal bg-brand-soft' : 'border-slate-200'}`}><input type="radio" name="cliente" value={client.id} checked={selected === client.id} onChange={() => setSelected(client.id)} /><span><strong className="block text-brand-navy">{client.nombre}</strong><span className="text-sm text-brand-muted">{client.codigo}</span></span></label>)}</div>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <button onClick={() => void enter()} disabled={!selected || busy} className="rounded-lg bg-brand-teal px-5 py-3 font-semibold text-white disabled:opacity-50">{busy ? 'Ingresando…' : 'Continuar'}</button>
  </section></main>
}
