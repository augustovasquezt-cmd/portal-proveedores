'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'

type Invoice = {
  id: string; numero: string; proveedor: { ruc: string; razon_social: string; email: string }; ruc_receptor: string | null; fecha_emision: string | null; moneda: string; monto_subtotal: number; monto_igv: number; monto_total: number; estado: string; pedidos: string[]; recibida_contabilidad_en: string | null; aceptada_portal_en: string | null; fecha_pago_programada: string | null; pagada_en: string | null; motivo_rechazo: string | null
  posiciones: { pedido: string; posicion: string; tipo: string; codigo: string; descripcion: string; unidad: string; cantidad: number; subtotal: number; igv: number; total: number }[]
  documentos_base: { tipo: string; numero: string; linea: string; cantidad: number }[]
  historial: { accion: string; estado_anterior: string | null; estado_nuevo: string; comentario: string | null; actor: string; fecha: string | null; fecha_pago_programada: string | null }[]
  adjuntos: { pdf: boolean; xml: boolean }
}

export default function RevisionFacturaPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const id = params.id
  const [invoice, setInvoice] = useState<Invoice | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [comment, setComment] = useState('')
  const [payDate, setPayDate] = useState('')
  const [pdfUrl, setPdfUrl] = useState('')
  const [xmlText, setXmlText] = useState('')
  const [preview, setPreview] = useState<'pdf' | 'xml' | ''>('')

  const load = useCallback(async () => {
    const token = localStorage.getItem('access_token')
    if (!token) { router.replace('/'); return }
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`http://localhost:8000/cuentas-por-pagar/facturas/${id}`, { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error((await response.json()).detail || 'No se pudo cargar la factura.')
      setInvoice(await response.json())
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Error de conexión.') }
    finally { setLoading(false) }
  }, [id, router])

  useEffect(() => {
    const timer = window.setTimeout(() => { void load() }, 0)
    return () => window.clearTimeout(timer)
  }, [load])
  useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl) }, [pdfUrl])

  async function showAttachment(type: 'pdf' | 'xml') {
    setError('')
    const token = localStorage.getItem('access_token') || ''
    try {
      const response = await fetch(`http://localhost:8000/cuentas-por-pagar/facturas/${id}/archivos/${type}`, { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error('No se pudo descargar el adjunto.')
      if (type === 'pdf') {
        if (pdfUrl) URL.revokeObjectURL(pdfUrl)
        setPdfUrl(URL.createObjectURL(await response.blob()))
      } else setXmlText(await response.text())
      setPreview(type)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Error al abrir el adjunto.') }
  }

  async function act(action: string) {
    if (!invoice) return
    if (action === 'rechazar' && comment.trim().length < 8) { setError('Escribe un motivo de rechazo de al menos 8 caracteres.'); return }
    if (action === 'programar_pago' && !payDate) { setError('Selecciona la fecha prevista de pago.'); return }
    setBusy(true); setError('')
    try {
      const response = await fetch(`http://localhost:8000/cuentas-por-pagar/facturas/${id}/acciones`, {
        method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ accion: action, comentario: comment, fecha_pago: payDate }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'No se pudo actualizar el estado.')
      setComment(''); await load()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Error al actualizar la factura.') }
    finally { setBusy(false) }
  }

  const formatDate = (value: string | null) => value ? new Date(value).toLocaleString('es-PE') : '—'
  const formatMoney = (value: number) => new Intl.NumberFormat('es-PE', { style: 'currency', currency: invoice?.moneda || 'PEN' }).format(value)
  const pending = ['Pendiente de revisión', 'Enviada a contabilidad', 'Pendiente de recepción'].includes(invoice?.estado || '')
  const received = invoice?.estado === 'Recibida por contabilidad'

  if (loading) return <p className="p-8 text-center text-slate-500">Cargando detalle de factura…</p>
  if (!invoice) return <div className="space-y-4"><Link href="/dashboard/cuentas-por-pagar" className="text-brand-teal">← Volver a la bandeja</Link><p role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">{error || 'Factura no encontrada.'}</p></div>

  return <div className="mx-auto max-w-7xl space-y-6">
    <Link href="/dashboard/cuentas-por-pagar" className="text-sm font-medium text-brand-teal hover:underline">← Volver a cuentas por pagar</Link>
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-semibold uppercase tracking-wide text-brand-teal">Revisión de comprobante</p><h1 className="mt-1 text-3xl font-bold text-brand-navy">{invoice.numero}</h1><p className="mt-2 text-slate-600">{invoice.proveedor.razon_social} · RUC {invoice.proveedor.ruc}</p></div><span className="rounded-full bg-brand-soft px-4 py-2 font-semibold text-brand-navy">{invoice.estado}</span></header>
    {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{error}</div>}

    <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-brand-navy">Datos del comprobante</h2>
        <dl className="grid gap-4 sm:grid-cols-2">{[
          ['Proveedor', invoice.proveedor.razon_social], ['RUC emisor', invoice.proveedor.ruc], ['Sociedad receptora', invoice.ruc_receptor || '—'], ['Fecha de emisión', invoice.fecha_emision || '—'], ['Moneda', invoice.moneda], ['Subtotal', formatMoney(invoice.monto_subtotal)], ['IGV', formatMoney(invoice.monto_igv)], ['Total', formatMoney(invoice.monto_total)], ['Pedido(s)', invoice.pedidos.join(', ') || '—'], ['Recibida por contabilidad', formatDate(invoice.recibida_contabilidad_en)], ['Aceptada en el portal', formatDate(invoice.aceptada_portal_en)], ['Pago programado', invoice.fecha_pago_programada || '—'], ['Pago registrado', formatDate(invoice.pagada_en)],
        ].map(([label, value]) => <div key={label}><dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 break-words font-medium text-slate-800">{value}</dd></div>)}</dl>
        {invoice.motivo_rechazo && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-800"><strong>Motivo del rechazo:</strong> {invoice.motivo_rechazo}</div>}
      </div>
      <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-brand-navy">Documentos adjuntos</h2>
        <div className="flex flex-wrap gap-2">{invoice.adjuntos.pdf && <button onClick={() => void showAttachment('pdf')} className="rounded-lg border border-brand-teal px-4 py-2 text-sm font-medium text-brand-teal">Ver factura PDF</button>}{invoice.adjuntos.xml && <button onClick={() => void showAttachment('xml')} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium">Ver XML SUNAT</button>}{!invoice.adjuntos.pdf && !invoice.adjuntos.xml && <p className="text-sm text-slate-500">No hay adjuntos para este registro.</p>}</div>
        {preview === 'pdf' && pdfUrl && <div className="overflow-hidden rounded-lg border border-slate-200"><iframe title="Vista previa de factura PDF" src={pdfUrl} className="h-[520px] w-full" /></div>}
        {preview === 'xml' && <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap break-all rounded-lg bg-slate-950 p-4 text-xs text-slate-100">{xmlText}</pre>}
      </div>
    </section>

    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-5 py-4"><h2 className="text-lg font-semibold text-brand-navy">Posiciones facturadas</h2><p className="mt-1 text-sm text-slate-500">Cantidades e importes asignados por pedido.</p></div>
      {invoice.posiciones.length === 0 ? <p className="p-5 text-sm text-slate-500">No hay detalle de posiciones en esta factura.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-sm"><thead className="bg-brand-soft text-left text-brand-navy"><tr>{['Pedido','Posición','Tipo / código','Descripción','Cantidad','Importe'].map(x => <th key={x} className="px-4 py-3">{x}</th>)}</tr></thead><tbody>{invoice.posiciones.map((line, i) => <tr key={`${line.pedido}-${line.posicion}-${i}`} className="border-t border-slate-100"><td className="px-4 py-3">{line.pedido}</td><td className="px-4 py-3">{line.posicion}</td><td className="px-4 py-3">{line.tipo === 'servicio' ? `Servicio · ${line.codigo}` : `Material · ${line.codigo}`}</td><td className="px-4 py-3">{line.descripcion}</td><td className="px-4 py-3">{line.cantidad} {line.unidad}</td><td className="px-4 py-3 font-medium">{formatMoney(line.total)}</td></tr>)}</tbody></table></div>}
      {invoice.documentos_base.length > 0 && <div className="border-t border-slate-200 p-5"><h3 className="mb-2 font-semibold text-brand-navy">Recepciones / conformidades asociadas</h3><ul className="space-y-1 text-sm text-slate-600">{invoice.documentos_base.map((doc, i) => <li key={`${doc.numero}-${i}`}>{doc.tipo}: {doc.numero} · línea {doc.linea} · cantidad {doc.cantidad}</li>)}</ul></div>}
    </section>

    <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
      <div className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-semibold text-brand-navy">Historial de gestión</h2>{invoice.historial.length === 0 ? <p className="mt-3 text-sm text-slate-500">Aún no hay acciones de contabilidad registradas.</p> : <ol className="mt-4 space-y-4">{invoice.historial.map((event, i) => <li key={i} className="border-l-2 border-brand-teal pl-4"><p className="font-medium text-brand-navy">{event.estado_nuevo}</p><p className="text-xs text-slate-500">{event.actor} · {formatDate(event.fecha)}</p>{event.comentario && <p className="mt-1 text-sm text-slate-700">{event.comentario}</p>}{event.fecha_pago_programada && <p className="text-sm text-slate-700">Pago programado: {event.fecha_pago_programada}</p>}</li>)}</ol>}</div>
      <div className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-semibold text-brand-navy">Acciones de cuentas por pagar</h2><p className="mt-1 text-sm text-slate-500">Cada cambio queda guardado en el historial de la factura.</p>
        {(pending || received) && <div className="mt-4 space-y-3"><label className="block text-sm font-medium text-brand-navy">Comentario o motivo de rechazo<textarea value={comment} onChange={e => setComment(e.target.value)} rows={3} maxLength={2000} placeholder="Describe una observación para el proveedor…" className="mt-1 w-full rounded-lg border border-slate-300 p-3 font-normal" /></label><div className="flex flex-wrap gap-2">{pending && <button disabled={busy} onClick={() => void act('recibir')} className="rounded-lg border border-brand-teal px-3 py-2 text-sm font-semibold text-brand-teal disabled:opacity-50">Marcar recibida</button>}{received && <button disabled={busy} onClick={() => void act('aceptar')} className="rounded-lg bg-brand-teal px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Aceptar factura</button>}<button disabled={busy} onClick={() => void act('rechazar')} className="rounded-lg border border-red-300 px-3 py-2 text-sm font-semibold text-red-700 disabled:opacity-50">Rechazar y observar</button></div></div>}
        {invoice.estado === 'Aceptada por contabilidad' && <div className="mt-4 flex flex-wrap items-end gap-3"><label className="text-sm font-medium text-brand-navy">Fecha de pago prevista<input type="date" min={new Date().toISOString().slice(0, 10)} value={payDate} onChange={e => setPayDate(e.target.value)} className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 font-normal" /></label><button disabled={busy} onClick={() => void act('programar_pago')} className="rounded-lg bg-brand-teal px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Programar pago</button></div>}
        {invoice.estado === 'Programada para pago' && <button disabled={busy} onClick={() => void act('marcar_pagada')} className="mt-4 rounded-lg bg-brand-teal px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Registrar pago realizado</button>}
        {!pending && !received && invoice.estado !== 'Aceptada por contabilidad' && invoice.estado !== 'Programada para pago' && <p className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">No hay acciones disponibles para este estado.</p>}
      </div>
    </section>
  </div>
}
