'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

type Summary = { facturas: Record<string, number>; montos: Record<string, number>; total: number }
type RecentInvoice = { id: string; numero: string; estado: string; monto_total: number; moneda: string; fecha_emision: string | null; proveedor: { razon_social: string; ruc: string } }

const cards = [
  { key: 'pendientes', label: 'Pendientes de recepción', filter: 'pendientes' },
  { key: 'recibidas', label: 'Recibidas por contabilidad', filter: 'recibidas' },
  { key: 'rechazadas', label: 'Rechazadas', filter: 'rechazadas' },
  { key: 'aceptadas', label: 'Aceptadas', filter: 'aceptadas' },
  { key: 'programadas', label: 'Programadas para pago', filter: 'programadas' },
  { key: 'pagadas', label: 'Pagadas', filter: 'pagadas' },
]

export default function InicioCuentasPorPagar() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [recent, setRecent] = useState<RecentInvoice[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const token = localStorage.getItem('access_token')
      const headers = { Authorization: `Bearer ${token || ''}` }
      Promise.all([
        fetch('http://localhost:8000/cuentas-por-pagar/resumen', { headers }),
        fetch('http://localhost:8000/cuentas-por-pagar/facturas?estado=todas&limit=8', { headers }),
      ]).then(async ([summaryResponse, recentResponse]) => {
        if (!summaryResponse.ok || !recentResponse.ok) throw new Error('No se pudo cargar el resumen de cuentas por pagar.')
        const [summaryData, recentData] = await Promise.all([summaryResponse.json(), recentResponse.json()])
        setSummary(summaryData)
        setRecent(recentData.items)
      }).catch(caught => setError(caught instanceof Error ? caught.message : 'Error al cargar el inicio.')).finally(() => setLoading(false))
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  const money = (amount: number) => new Intl.NumberFormat('es-PE', { style: 'currency', currency: 'PEN' }).format(amount)
  const date = (value: string | null) => value ? new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString('es-PE') : '—'

  return <div className="mx-auto max-w-7xl space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-semibold uppercase tracking-wide text-brand-teal">Panel de trabajo</p><h1 className="mt-1 text-3xl font-bold text-brand-navy">Inicio · Cuentas por pagar</h1><p className="mt-2 text-slate-600">Sigue las facturas desde su recepción hasta el pago.</p></div><Link href="/dashboard/cuentas-por-pagar/comprobantes" className="rounded-lg bg-brand-teal px-4 py-2 font-semibold text-white">Ver comprobantes</Link></header>
    {error && <div role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">{error}</div>}
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{cards.map(card => <Link key={card.key} href={`/dashboard/cuentas-por-pagar/comprobantes?estado=${card.filter}`} className="rounded-xl border border-slate-200 bg-white p-5 transition hover:border-brand-teal hover:shadow-sm"><span className="text-sm text-slate-600">{card.label}</span><strong className="mt-2 block text-3xl text-brand-navy">{loading ? '—' : summary?.facturas[card.key] ?? 0}</strong><span className="mt-1 block text-sm text-slate-500">{summary ? money(summary.montos[card.key] || 0) : 'Importe total'}</span></Link>)}</section>
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="flex items-center justify-between border-b border-slate-200 px-5 py-4"><div><h2 className="font-semibold text-brand-navy">Comprobantes recientes</h2><p className="mt-1 text-sm text-slate-500">Últimos registros ingresados al portal.</p></div><Link href="/dashboard/cuentas-por-pagar/comprobantes" className="text-sm font-semibold text-brand-teal hover:underline">Ver todos</Link></div>
      {loading ? <p className="p-6 text-slate-500">Cargando actividad…</p> : recent.length === 0 ? <p className="p-8 text-center text-slate-500">Aún no hay comprobantes registrados.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[700px] text-sm"><thead className="bg-brand-soft text-left text-brand-navy"><tr><th className="px-5 py-3">Comprobante</th><th className="px-5 py-3">Proveedor</th><th className="px-5 py-3">Emisión</th><th className="px-5 py-3">Total</th><th className="px-5 py-3">Estado</th><th className="px-5 py-3">Acción</th></tr></thead><tbody>{recent.map(invoice => <tr key={invoice.id} className="border-t border-slate-100"><td className="px-5 py-3 font-semibold">{invoice.numero}</td><td className="px-5 py-3">{invoice.proveedor.razon_social}<span className="block text-xs text-slate-500">RUC {invoice.proveedor.ruc}</span></td><td className="px-5 py-3">{date(invoice.fecha_emision)}</td><td className="px-5 py-3">{money(invoice.monto_total)}</td><td className="px-5 py-3">{invoice.estado}</td><td className="px-5 py-3"><Link href={`/dashboard/cuentas-por-pagar/${invoice.id}`} className="font-semibold text-brand-teal">Consultar</Link></td></tr>)}</tbody></table></div>}
    </section>
  </div>
}
