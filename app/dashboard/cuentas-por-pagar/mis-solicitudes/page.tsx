'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'

type RequestRow = { id: string; categoria: string; asunto: string; descripcion: string; estado: string; creado_en: string | null; factura_id: string | null; factura: string | null }
type InvoiceOption = { id: string; numero: string; proveedor: { razon_social: string } }
const categories = ['Consulta de factura', 'Problema de pago', 'Datos maestros', 'Acceso al portal', 'Otra consulta']

export default function MisSolicitudesPage() {
  const [requests, setRequests] = useState<RequestRow[]>([])
  const [invoices, setInvoices] = useState<InvoiceOption[]>([])
  const [category, setCategory] = useState(categories[0])
  const [subject, setSubject] = useState('')
  const [description, setDescription] = useState('')
  const [invoiceId, setInvoiceId] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    const headers = { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` }
    try {
      const [requestsResponse, invoiceResponse] = await Promise.all([
        fetch('http://localhost:8000/cuentas-por-pagar/solicitudes', { headers }),
        fetch('http://localhost:8000/cuentas-por-pagar/facturas?estado=todas&limit=100', { headers }),
      ])
      if (!requestsResponse.ok || !invoiceResponse.ok) throw new Error('No se pudieron cargar las solicitudes.')
      const [requestData, invoiceData] = await Promise.all([requestsResponse.json(), invoiceResponse.json()])
      setRequests(requestData)
      setInvoices(invoiceData.items)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Error al consultar las solicitudes.') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { const timer = window.setTimeout(() => { void load() }, 0); return () => window.clearTimeout(timer) }, [load])

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError(''); setNotice('')
    try {
      const response = await fetch('http://localhost:8000/cuentas-por-pagar/solicitudes', {
        method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ categoria: category, asunto: subject, descripcion: description, factura_id: invoiceId || null }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'No se pudo registrar la solicitud.')
      setSubject(''); setDescription(''); setInvoiceId(''); setNotice('Solicitud registrada correctamente.'); await load()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Error al registrar la solicitud.') }
    finally { setSaving(false) }
  }

  const date = (value: string | null) => value ? new Date(value).toLocaleString('es-PE') : '—'
  return <div className="mx-auto max-w-6xl space-y-6"><header><p className="text-sm font-semibold uppercase tracking-wide text-brand-teal">Ayuda interna</p><h1 className="mt-1 text-3xl font-bold text-brand-navy">Mis solicitudes</h1><p className="mt-2 text-slate-600">Registra consultas vinculadas a una factura y conserva su seguimiento.</p></header>
    {error && <div role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">{error}</div>}{notice && <div role="status" className="rounded-lg bg-emerald-50 p-4 text-emerald-800">{notice}</div>}
    <section className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
      <form onSubmit={submit} className="space-y-4 rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-semibold text-brand-navy">Nueva solicitud</h2><label className="block text-sm font-medium text-brand-navy">Categoría<select value={category} onChange={e => setCategory(e.target.value)} className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal">{categories.map(item => <option key={item}>{item}</option>)}</select></label><label className="block text-sm font-medium text-brand-navy">Factura relacionada (opcional)<select value={invoiceId} onChange={e => setInvoiceId(e.target.value)} className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"><option value="">Sin factura</option>{invoices.map(invoice => <option key={invoice.id} value={invoice.id}>{invoice.numero} · {invoice.proveedor.razon_social}</option>)}</select></label><label className="block text-sm font-medium text-brand-navy">Asunto<input required maxLength={200} value={subject} onChange={e => setSubject(e.target.value)} className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal" placeholder="Resume tu consulta" /></label><label className="block text-sm font-medium text-brand-navy">Descripción<textarea required minLength={10} maxLength={3000} rows={5} value={description} onChange={e => setDescription(e.target.value)} className="mt-1 block w-full rounded-lg border border-slate-300 p-3 font-normal" placeholder="Incluye el contexto necesario para ayudarte." /><span className="mt-1 block text-xs font-normal text-slate-500">Entre 10 y 3000 caracteres.</span></label><button disabled={saving} className="rounded-lg bg-brand-teal px-4 py-2 font-semibold text-white disabled:opacity-50">{saving ? 'Enviando…' : 'Enviar solicitud'}</button></form>
      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="border-b border-slate-200 px-5 py-4"><h2 className="font-semibold text-brand-navy">Solicitudes enviadas</h2><p className="mt-1 text-sm text-slate-500">Consultas asociadas a tu usuario.</p></div>{loading ? <p className="p-5 text-slate-500">Cargando solicitudes…</p> : requests.length === 0 ? <p className="p-8 text-center text-slate-500">Aún no has enviado solicitudes.</p> : <ul className="divide-y divide-slate-100">{requests.map(request => <li key={request.id} className="p-5"><div className="flex flex-wrap justify-between gap-2"><div><p className="font-semibold text-brand-navy">{request.asunto}</p><p className="mt-1 text-xs text-slate-500">{request.categoria} · {date(request.creado_en)}{request.factura && request.factura_id && <> · <Link className="text-brand-teal hover:underline" href={`/dashboard/cuentas-por-pagar/${request.factura_id}`}>{request.factura}</Link></>}</p></div><span className="h-fit rounded-full bg-slate-100 px-3 py-1 text-xs">{request.estado}</span></div><p className="mt-3 whitespace-pre-wrap text-sm text-slate-700">{request.descripcion}</p></li>)}</ul>}</section>
    </section>
  </div>
}
