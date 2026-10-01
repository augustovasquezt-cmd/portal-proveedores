'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'

type InboxStatus = 'todas' | 'pendientes' | 'recibidas' | 'aceptadas' | 'programadas' | 'pagadas' | 'rechazadas'
type Invoice = { id: string; numero: string; proveedor: { ruc: string; razon_social: string }; ruc_receptor: string | null; fecha_emision: string | null; monto_total: number; moneda: string; estado: string; creado_en: string | null; fecha_pago_programada: string | null; pedidos: string[]; tiene_pdf: boolean; tiene_xml: boolean }
type Summary = { facturas: Record<string, number>; montos: Record<string, number>; total: number }

const tabs: { id: InboxStatus; label: string; metric: string }[] = [
  { id: 'pendientes', label: 'Pendientes', metric: 'pendientes' },
  { id: 'recibidas', label: 'Recibidas', metric: 'recibidas' },
  { id: 'aceptadas', label: 'Aceptadas', metric: 'aceptadas' },
  { id: 'programadas', label: 'Programadas', metric: 'programadas' },
  { id: 'pagadas', label: 'Pagadas', metric: 'pagadas' },
  { id: 'rechazadas', label: 'Rechazadas', metric: 'rechazadas' },
]

export default function CuentasPorPagarPage() {
  const router = useRouter()
  const [summary, setSummary] = useState<Summary | null>(null)
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState<InboxStatus>('pendientes')
  const [search, setSearch] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [recipient, setRecipient] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get('estado') as InboxStatus | null
    const timer = window.setTimeout(() => {
      if (initial && ['todas', 'pendientes', 'recibidas', 'aceptadas', 'programadas', 'pagadas', 'rechazadas'].includes(initial)) setStatus(initial)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  const load = useCallback(async () => {
    const token = localStorage.getItem('access_token')
    setLoading(true)
    setError('')
    setSummary(null)
    if (!token) {
      setError('Tu sesión expiró. Inicia sesión nuevamente para consultar la bandeja.')
      setInvoices([])
      setTotal(0)
      setLoading(false)
      return
    }
    const headers = { Authorization: `Bearer ${token}` }
    try {
      const query = new URLSearchParams({ estado: status, buscar: search, limit: '50', offset: String(offset) })
      if (from) query.set('desde', from)
      if (to) query.set('hasta', to)
      if (recipient) query.set('receptor', recipient)
      const [summaryResponse, invoicesResponse] = await Promise.all([
        fetch('/api-backend/cuentas-por-pagar/resumen', { headers }),
        fetch(`/api-backend/cuentas-por-pagar/facturas?${query.toString()}`, { headers }),
      ])
      if (!summaryResponse.ok || !invoicesResponse.ok) {
        const failedResponse = !summaryResponse.ok ? summaryResponse : invoicesResponse
        if (failedResponse.status === 401) {
          for (const key of ['access_token', 'user_role', 'client_id', 'client_name', 'available_clients', 'password_change_required', 'ruc', 'razon_social']) {
            localStorage.removeItem(key)
          }
          router.replace('/?sesion=expirada')
          return
        }
        let detail = ''
        try {
          const body = await failedResponse.json()
          detail = typeof body.detail === 'string' ? body.detail : ''
        } catch { /* Keep the friendly fallback below. */ }
        throw new Error(detail || `No se pudo consultar la bandeja (HTTP ${failedResponse.status}).`)
      }
      const [summaryData, invoiceData] = await Promise.all([summaryResponse.json(), invoicesResponse.json()])
      setSummary(summaryData)
      setInvoices(invoiceData.items)
      setTotal(invoiceData.total)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Error al cargar las facturas.')
      setInvoices([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [status, search, from, to, recipient, offset, router])

  useEffect(() => {
    const timer = window.setTimeout(() => { void load() }, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const formatMoney = (amount: number, currency: string) => new Intl.NumberFormat('es-PE', { style: 'currency', currency: currency || 'PEN' }).format(amount)
  const formatDate = (value: string | null) => value ? new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString('es-PE') : '—'

  return <div className="mx-auto max-w-7xl space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-sm font-semibold uppercase tracking-wide text-brand-teal">Gestión interna</p><h1 className="mt-1 text-3xl font-bold text-brand-navy">Mis comprobantes</h1><p className="mt-2 text-gray-600">Consulta todas las facturas y filtra su estado hasta el pago.</p></div>
      <button onClick={() => void load()} className="rounded-lg border border-brand-teal px-4 py-2 font-medium text-brand-teal hover:bg-brand-soft">Actualizar</button>
    </header>

    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {tabs.map(tab => <button key={tab.id} onClick={() => { setStatus(tab.id); setOffset(0) }} aria-pressed={status === tab.id} className={`rounded-xl border bg-white p-4 text-left transition ${status === tab.id ? 'border-brand-teal ring-2 ring-brand-teal/20' : 'border-slate-200 hover:border-brand-teal/60'}`}>
        <span className="text-sm text-slate-600">{tab.label}</span><span className="mt-1 block text-2xl font-bold text-brand-navy">{summary?.facturas[tab.metric] ?? (loading || error ? '—' : '0')}</span><span className="text-xs text-slate-500">{summary ? formatMoney(summary.montos[tab.metric] || 0, 'PEN') : loading ? 'Cargando…' : error ? 'No disponible' : formatMoney(0, 'PEN')}</span>
      </button>)}
    </section>

    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="grid gap-4 md:grid-cols-[minmax(220px,2fr)_1fr_1fr_1fr_auto] md:items-end">
        <label className="text-sm font-medium text-brand-navy">Buscar comprobante, proveedor, RUC o pedido<input value={search} onChange={e => { setSearch(e.target.value); setOffset(0) }} placeholder="Serie, proveedor o pedido" className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 font-normal" /></label>
        <label className="text-sm font-medium text-brand-navy">Emisión desde<input type="date" value={from} onChange={e => { setFrom(e.target.value); setOffset(0) }} className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal" /></label>
        <label className="text-sm font-medium text-brand-navy">Emisión hasta<input type="date" value={to} onChange={e => { setTo(e.target.value); setOffset(0) }} className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal" /></label>
        <label className="text-sm font-medium text-brand-navy">RUC sociedad destino<input inputMode="numeric" maxLength={11} value={recipient} onChange={e => { setRecipient(e.target.value.replace(/\D/g, '')); setOffset(0) }} placeholder="11 dígitos" className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal" /></label>
        <button onClick={() => { setSearch(''); setFrom(''); setTo(''); setRecipient(''); setOffset(0) }} className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50">Limpiar</button>
      </div>
    </section>

    {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{error}</div>}
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-5 py-4"><h2 className="font-semibold text-brand-navy">{tabs.find(t => t.id === status)?.label || 'Todas las facturas'} <span className="font-normal text-slate-500">· {loading ? 'Cargando…' : `${total} resultados`}</span></h2></div>
      {loading ? <p className="p-8 text-center text-slate-500">Cargando comprobantes…</p> : invoices.length === 0 ? <div className="p-10 text-center"><h3 className="font-semibold text-brand-navy">No hay facturas en esta bandeja</h3><p className="mt-1 text-sm text-slate-500">Las facturas preregistradas por proveedores aparecerán aquí.</p></div> : <><div className="overflow-x-auto"><table className="w-full min-w-[900px] text-sm"><thead className="bg-brand-soft text-left text-brand-navy"><tr>{['Comprobante','Proveedor','Sociedad destino','Emisión','Pedido(s)','Importe','Estado','Acción'].map(x => <th key={x} className="px-4 py-3 font-semibold">{x}</th>)}</tr></thead><tbody>{invoices.map(invoice => <tr key={invoice.id} className="border-t border-slate-100 hover:bg-slate-50"><td className="px-4 py-4"><span className="font-semibold text-brand-navy">{invoice.numero}</span><div className="mt-1 flex gap-2 text-xs text-slate-500">{invoice.tiene_xml && <span>XML</span>}{invoice.tiene_pdf && <span>PDF</span>}</div></td><td className="px-4 py-4"><span className="font-medium">{invoice.proveedor.razon_social}</span><div className="text-xs text-slate-500">RUC {invoice.proveedor.ruc}</div></td><td className="px-4 py-4">{invoice.ruc_receptor || '—'}</td><td className="px-4 py-4">{formatDate(invoice.fecha_emision)}</td><td className="px-4 py-4">{invoice.pedidos.length ? invoice.pedidos.join(', ') : '—'}</td><td className="px-4 py-4 font-semibold">{formatMoney(invoice.monto_total, invoice.moneda)}</td><td className="px-4 py-4"><span className="rounded-full bg-slate-100 px-3 py-1 text-xs">{invoice.estado}</span></td><td className="px-4 py-4"><Link className="font-semibold text-brand-teal hover:underline" href={`/dashboard/cuentas-por-pagar/${invoice.id}`}>Revisar</Link></td></tr>)}</tbody></table></div><div className="flex items-center justify-between border-t border-slate-200 px-5 py-3 text-sm text-slate-600"><span>Mostrando {offset + 1}–{Math.min(offset + invoices.length, total)} de {total}</span><div className="flex gap-2"><button disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 50))} className="rounded border border-slate-300 px-3 py-1 disabled:opacity-40">Anterior</button><button disabled={offset + 50 >= total || loading} onClick={() => setOffset(offset + 50)} className="rounded border border-slate-300 px-3 py-1 disabled:opacity-40">Siguiente</button></div></div></>}
    </section>
  </div>
}
