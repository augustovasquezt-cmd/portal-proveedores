'use client'

import { ChangeEvent, FormEvent, useCallback, useEffect, useState } from 'react'

const API_BASE = '/api-backend'
const API = `${API_BASE}/cuentas-por-pagar/sin-oc`
type Society = { id: string; ruc: string; razon_social: string }
type Invoice = {
  id: string; numero: string; proveedor_ruc: string; proveedor_razon_social: string; fecha_emision: string
  moneda: string; categoria: string; monto_subtotal: number; monto_igv: number; monto_total: number
  centro_costo: string | null; cuenta_contable: string | null; periodo_servicio: string | null
  estado: string; origen: string; sociedad_id: string; tiene_xml: boolean; tiene_pdf: boolean
  nombre_xml: string | null; nombre_pdf: string | null; observacion: string | null
}
type BatchItem = { archivo: string; estado: string; detalle?: string; advertencias?: string[]; factura?: Invoice }

const categories = ['Servicios básicos', 'Servicios profesionales', 'Alquileres', 'Tributos y tasas', 'Otros']

export default function FacturasSinOrdenPage() {
  const [societies, setSocieties] = useState<Society[]>([])
  const [items, setItems] = useState<Invoice[]>([])
  const [selected, setSelected] = useState<Invoice | null>(null)
  const [filePreview, setFilePreview] = useState<{ url: string; kind: 'pdf' | 'xml'; name: string } | null>(null)
  const [xmlFiles, setXmlFiles] = useState<File[]>([])
  const [pdfFiles, setPdfFiles] = useState<File[]>([])
  const [manifestFile, setManifestFile] = useState<File | null>(null)
  const [batchPdfs, setBatchPdfs] = useState<File[]>([])
  const [societyId, setSocietyId] = useState('')
  const [category, setCategory] = useState('Servicios básicos')
  const [description, setDescription] = useState('')
  const [mode, setMode] = useState<'lote' | 'lote_pdf' | 'manual'>('lote')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('todas')
  const [filterSociety, setFilterSociety] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [batch, setBatch] = useState<BatchItem[]>([])
  const [manual, setManual] = useState({ proveedor_ruc: '', proveedor_razon_social: '', serie: '', correlativo: '', fecha_emision: '', moneda: 'PEN', monto_subtotal: '0', monto_igv: '0', monto_total: '' })
  const [accounting, setAccounting] = useState({ centro_costo: '', cuenta_contable: '', periodo_servicio: '' })
  const [manualPdf, setManualPdf] = useState<File | null>(null)

  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` })
  async function responseMessage(response: Response) {
    try { const data = await response.json(); return typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data) }
    catch { return `Error HTTP ${response.status}` }
  }
  async function apiFetch(input: RequestInfo | URL, init?: RequestInit) {
    try { return await fetch(input, init) }
    catch (caught) {
      if (caught instanceof TypeError) {
        throw new Error(`No se pudo contactar con el backend a través del portal (${API_BASE}). Verifica que FastAPI esté activo en el servidor configurado.`)
      }
      throw caught
    }
  }
  const loadData = useCallback(async () => {
    const authHeaders = headers()
    const [societyResponse, listResponse] = await Promise.all([
      apiFetch(`${API}/sociedades`, { headers: authHeaders }),
      apiFetch(`${API}?estado=${encodeURIComponent(status)}&buscar=${encodeURIComponent(search)}&sociedad_id=${encodeURIComponent(filterSociety)}`, { headers: authHeaders }),
    ])
    if (!societyResponse.ok) throw new Error(await responseMessage(societyResponse))
    if (!listResponse.ok) throw new Error(await responseMessage(listResponse))
    const [societyData, listData] = await Promise.all([societyResponse.json(), listResponse.json()])
    setSocieties(societyData)
    setItems(listData.items || [])
    setSocietyId(current => current || societyData[0]?.id || '')
  }, [filterSociety, search, status])
  useEffect(() => {
    const timer = window.setTimeout(() => { loadData().catch(e => setError(e.message)).finally(() => setLoading(false)) }, 0)
    return () => window.clearTimeout(timer)
  }, [loadData])

  const money = (amount: number, currency = 'PEN') => new Intl.NumberFormat('es-PE', { style: 'currency', currency, minimumFractionDigits: 2 }).format(amount)
  const inputClass = 'mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-brand-teal focus:ring-2 focus:ring-brand-teal/20'

  async function submitBatch(event: FormEvent) {
    event.preventDefault(); setError(''); setNotice(''); setBatch([])
    if (!societyId) { setError('Selecciona la sociedad receptora.'); return }
    if (!xmlFiles.length) { setError('Selecciona al menos un XML para iniciar el lote.'); return }
    if (xmlFiles.length > 30 || pdfFiles.length > 30) { setError('El límite es 30 XML y 30 PDF por lote.'); return }
    setBusy(true)
    const form = new FormData(); form.append('sociedad_id', societyId); form.append('categoria', category); form.append('descripcion', description)
    Object.entries(accounting).forEach(([key, value]) => form.append(key, value))
    xmlFiles.forEach(file => form.append('xml_files', file)); pdfFiles.forEach(file => form.append('pdf_files', file))
    try {
      const response = await apiFetch(`${API}/lote`, { method: 'POST', headers: headers(), body: form })
      if (!response.ok) throw new Error(await responseMessage(response))
      const result = await response.json(); setBatch(result.items || [])
      setNotice(`Lote procesado: ${result.registradas} de ${xmlFiles.length} facturas registradas. Revisa las advertencias y errores antes de continuar.`)
      setXmlFiles([]); setPdfFiles([]); setDescription(''); await loadData()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo procesar el lote.') }
    finally { setBusy(false) }
  }

  async function submitManual(event: FormEvent) {
    event.preventDefault(); setError(''); setNotice('')
    if (!manualPdf) { setError('Adjunta el PDF o recibo del comprobante.'); return }
    setBusy(true)
    const form = new FormData(); form.append('sociedad_id', societyId); form.append('categoria', category); form.append('descripcion', description)
    Object.entries(accounting).forEach(([key, value]) => form.append(key, value))
    Object.entries(manual).forEach(([key, value]) => form.append(key, value)); form.append('pdf', manualPdf)
    try {
      const response = await apiFetch(`${API}/manual`, { method: 'POST', headers: headers(), body: form })
      if (!response.ok) throw new Error(await responseMessage(response))
      const saved: Invoice = await response.json(); setSelected(saved); setNotice(`Comprobante ${saved.numero} registrado para revisión. El PDF queda adjunto al expediente.`)
      setManual({ proveedor_ruc: '', proveedor_razon_social: '', serie: '', correlativo: '', fecha_emision: '', moneda: 'PEN', monto_subtotal: '0', monto_igv: '0', monto_total: '' }); setManualPdf(null); setAccounting({ centro_costo: '', cuenta_contable: '', periodo_servicio: '' })
      await loadData()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo registrar el comprobante.') }
    finally { setBusy(false) }
  }

  function downloadCsvTemplate() {
    const csv = 'pdf_filename,proveedor_ruc,proveedor_razon_social,serie,correlativo,fecha_emision,moneda,categoria,monto_subtotal,monto_igv,monto_total,centro_costo,cuenta_contable,periodo_servicio,descripcion\nrecibo-agua.pdf,20123456789,Empresa de Servicios,F001,42,2026-09-29,PEN,Servicios básicos,100.00,18.00,118.00,CC-10,631100,09/2026,Servicio de agua\n'
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); const link = document.createElement('a')
    link.href = url; link.download = 'plantilla-facturas-sin-oc.csv'; link.click(); URL.revokeObjectURL(url)
  }

  async function submitPdfBatch(event: FormEvent) {
    event.preventDefault(); setError(''); setNotice(''); setBatch([])
    if (!societyId) { setError('Selecciona la sociedad receptora.'); return }
    if (!manifestFile || !batchPdfs.length) { setError('Selecciona el CSV y los archivos PDF que referencia.'); return }
    if (batchPdfs.length > 30) { setError('El límite es 30 PDF por lote.'); return }
    setBusy(true)
    const form = new FormData(); form.append('sociedad_id', societyId); form.append('manifiesto', manifestFile); batchPdfs.forEach(file => form.append('pdf_files', file))
    try {
      const response = await apiFetch(`${API}/lote-pdf`, { method: 'POST', headers: headers(), body: form })
      if (!response.ok) throw new Error(await responseMessage(response))
      const result = await response.json(); setBatch(result.items || [])
      setNotice(`Lote procesado: ${result.registradas} de ${batchPdfs.length} recibos registrados. Revisa errores y advertencias antes de aprobarlos.`)
      setManifestFile(null); setBatchPdfs([]); await loadData()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo procesar el lote PDF.') }
    finally { setBusy(false) }
  }

  async function action(invoice: Invoice, accion: string) {
    setError(''); setNotice('')
    const comentario = accion === 'rechazar' ? window.prompt('Indica un motivo claro para rechazar el comprobante:') || '' : ''
    if (accion === 'rechazar' && comentario.trim().length < 8) return
    if (accion === 'aprobar' && !window.confirm('¿Confirmas que Contabilidad revisó los datos y aprueba este comprobante para integración SAP?')) return
    setBusy(true)
    try {
      const response = await apiFetch(`${API}/${invoice.id}/acciones`, { method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify({ accion, comentario }) })
      if (!response.ok) throw new Error(await responseMessage(response))
      setNotice(`Estado actualizado para ${invoice.numero}.`); setSelected(null); await loadData()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo actualizar el estado.') }
    finally { setBusy(false) }
  }

  async function openFile(invoice: Invoice, kind: 'pdf' | 'xml') {
    setError('')
    try {
      const response = await apiFetch(`${API}/${invoice.id}/archivos/${kind}`, { headers: headers() })
      if (!response.ok) throw new Error(await responseMessage(response))
      const blob = await response.blob(); const url = URL.createObjectURL(blob)
      setFilePreview({ url, kind, name: kind === 'pdf' ? invoice.nombre_pdf || 'Factura.pdf' : invoice.nombre_xml || 'Factura.xml' })
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo abrir el adjunto.') }
  }

  async function selectInvoice(invoice: Invoice) {
    try {
      const response = await apiFetch(`${API}/${invoice.id}`, { headers: headers() })
      if (!response.ok) throw new Error(await responseMessage(response))
      setSelected(await response.json())
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo consultar el comprobante.') }
  }

  return <div className="mx-auto max-w-7xl space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-semibold uppercase tracking-wide text-brand-teal">Recepción interna</p><h1 className="mt-1 text-3xl font-bold text-brand-navy">Facturas sin OC/OS</h1><p className="mt-2 max-w-3xl text-slate-600">Registra servicios y comprobantes que no nacen de un pedido en SAP, como agua, luz, telefonía, alquileres y tributos.</p></div><span className="rounded-full bg-brand-soft px-3 py-1.5 text-sm font-semibold text-brand-navy">Solo Cuentas por pagar</span></header>
    {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}
    {notice && <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">{notice}</div>}

    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-4"><div><h2 className="text-lg font-semibold text-brand-navy">Ingreso de comprobantes</h2><p className="mt-1 text-sm text-slate-600">El ingreso queda como pendiente de revisión. Aprobarlo no contabiliza ni envía nada a SAP todavía.</p><p className="mt-1 text-xs text-slate-500">La lectura del XML prellena datos y ayuda a detectar inconsistencias; no verifica la aceptación del comprobante en SUNAT ni sustituye la revisión tributaria.</p></div><div className="flex flex-wrap rounded-lg bg-slate-100 p-1"><button type="button" onClick={() => setMode('lote')} className={`rounded-md px-3 py-2 text-sm font-semibold ${mode === 'lote' ? 'bg-white text-brand-navy shadow-sm' : 'text-slate-600'}`}>Lote XML</button><button type="button" onClick={() => setMode('lote_pdf')} className={`rounded-md px-3 py-2 text-sm font-semibold ${mode === 'lote_pdf' ? 'bg-white text-brand-navy shadow-sm' : 'text-slate-600'}`}>Lote CSV + PDF</button><button type="button" onClick={() => setMode('manual')} className={`rounded-md px-3 py-2 text-sm font-semibold ${mode === 'manual' ? 'bg-white text-brand-navy shadow-sm' : 'text-slate-600'}`}>PDF individual</button></div></div>
      <div className="mt-5 grid gap-4 md:grid-cols-2"><label className="text-sm font-semibold text-slate-700">Sociedad receptora<select className={inputClass} value={societyId} onChange={e => setSocietyId(e.target.value)}>{societies.map(s => <option key={s.id} value={s.id}>{s.razon_social} · RUC {s.ruc}</option>)}</select></label><label className="text-sm font-semibold text-slate-700">Tipo de gasto<select className={inputClass} value={category} onChange={e => setCategory(e.target.value)}>{categories.map(c => <option key={c}>{c}</option>)}</select></label></div>
      <div className="mt-4 grid gap-4 md:grid-cols-3"><label className="text-sm font-semibold text-slate-700">Centro de costo (opcional)<input className={inputClass} maxLength={80} value={accounting.centro_costo} onChange={e => setAccounting({...accounting, centro_costo: e.target.value})} placeholder="Código SAP" /></label><label className="text-sm font-semibold text-slate-700">Cuenta contable (opcional)<input className={inputClass} maxLength={80} value={accounting.cuenta_contable} onChange={e => setAccounting({...accounting, cuenta_contable: e.target.value})} placeholder="Cuenta de mayor" /></label><label className="text-sm font-semibold text-slate-700">Periodo del servicio<input className={inputClass} maxLength={20} value={accounting.periodo_servicio} onChange={e => setAccounting({...accounting, periodo_servicio: e.target.value})} placeholder="Ej.: 09/2026" /></label></div>
      {mode === 'lote' ? <form onSubmit={submitBatch} className="mt-4 space-y-4"><label className="block text-sm font-semibold text-slate-700">XML de facturas (hasta 30 por lote, 5 MB cada uno)<input className={inputClass} type="file" accept=".xml,application/xml,text/xml" multiple onChange={(e: ChangeEvent<HTMLInputElement>) => setXmlFiles(Array.from(e.target.files || []))} /></label><label className="block text-sm font-semibold text-slate-700">PDF de respaldo, opcional (se vincula si el nombre base coincide con el XML)<input className={inputClass} type="file" accept=".pdf,application/pdf" multiple onChange={(e: ChangeEvent<HTMLInputElement>) => setPdfFiles(Array.from(e.target.files || []))} /></label><p className="text-xs text-slate-500">Máximo 30 MB por lote. Ejemplo de vínculo: recibo-agua.xml con recibo-agua.pdf. Los archivos sin pareja se reportan y no se adjuntan a otra factura.</p><label className="block text-sm font-semibold text-slate-700">Referencia interna opcional<input className={inputClass} value={description} onChange={e => setDescription(e.target.value)} placeholder="Ej.: recibos de servicios de septiembre" maxLength={500} /></label><button disabled={busy || !societies.length} className="rounded-lg bg-brand-teal px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{busy ? 'Procesando lote…' : 'Procesar y registrar lote'}</button></form> : mode === 'lote_pdf' ? <form onSubmit={submitPdfBatch} className="mt-4 space-y-4"><div><button type="button" onClick={downloadCsvTemplate} className="text-sm font-semibold text-brand-teal underline">Descargar plantilla CSV</button><p className="mt-1 text-xs text-slate-500">Completa una fila por recibo, indicando el nombre exacto del PDF. Usa fechas YYYY-MM-DD y guarda el CSV en UTF-8.</p></div><label className="block text-sm font-semibold text-slate-700">Manifiesto CSV (máximo 1 MB)<input required className={inputClass} type="file" accept=".csv,text/csv" onChange={e => setManifestFile(e.target.files?.[0] || null)} /></label><label className="block text-sm font-semibold text-slate-700">PDF / recibos (hasta 30 archivos, 5 MB cada uno)<input required className={inputClass} type="file" accept=".pdf,application/pdf" multiple onChange={e => setBatchPdfs(Array.from(e.target.files || []))} /></label><p className="text-xs text-slate-500">Máximo 30 MB por lote. Cada PDF se asocia exclusivamente con el nombre indicado en la fila CSV; los fallidos se reportan por fila y los registros correctos quedan en revisión.</p><button disabled={busy || !societies.length} className="rounded-lg bg-brand-teal px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{busy ? 'Procesando lote…' : 'Procesar lote CSV + PDF'}</button></form> : <form onSubmit={submitManual} className="mt-4 space-y-4"><div className="grid gap-4 md:grid-cols-3"><label className="text-sm font-semibold text-slate-700">RUC proveedor<input required pattern="[0-9]{11}" maxLength={11} className={inputClass} value={manual.proveedor_ruc} onChange={e => setManual({...manual, proveedor_ruc: e.target.value})} /></label><label className="text-sm font-semibold text-slate-700 md:col-span-2">Razón social<input required maxLength={200} className={inputClass} value={manual.proveedor_razon_social} onChange={e => setManual({...manual, proveedor_razon_social: e.target.value})} /></label><label className="text-sm font-semibold text-slate-700">Serie<input required maxLength={10} className={inputClass} value={manual.serie} onChange={e => setManual({...manual, serie: e.target.value})} /></label><label className="text-sm font-semibold text-slate-700">Correlativo<input required inputMode="numeric" className={inputClass} value={manual.correlativo} onChange={e => setManual({...manual, correlativo: e.target.value})} /></label><label className="text-sm font-semibold text-slate-700">Fecha de emisión<input required type="date" className={inputClass} value={manual.fecha_emision} onChange={e => setManual({...manual, fecha_emision: e.target.value})} /></label><label className="text-sm font-semibold text-slate-700">Moneda<input required maxLength={3} className={inputClass} value={manual.moneda} onChange={e => setManual({...manual, moneda: e.target.value.toUpperCase()})} /></label><label className="text-sm font-semibold text-slate-700">Subtotal<input required type="number" min="0" step="0.01" className={inputClass} value={manual.monto_subtotal} onChange={e => setManual({...manual, monto_subtotal: e.target.value})} /></label><label className="text-sm font-semibold text-slate-700">IGV / impuestos<input required type="number" min="0" step="0.01" className={inputClass} value={manual.monto_igv} onChange={e => setManual({...manual, monto_igv: e.target.value})} /></label><label className="text-sm font-semibold text-slate-700">Total del comprobante<input required type="number" min="0.01" step="0.01" className={inputClass} value={manual.monto_total} onChange={e => setManual({...manual, monto_total: e.target.value})} /></label></div><label className="block text-sm font-semibold text-slate-700">PDF o recibo (máximo 5 MB)<input required className={inputClass} type="file" accept=".pdf,application/pdf" onChange={e => setManualPdf(e.target.files?.[0] || null)} /></label><label className="block text-sm font-semibold text-slate-700">Referencia interna<input className={inputClass} maxLength={500} value={description} onChange={e => setDescription(e.target.value)} placeholder="Ej.: suministro eléctrico de oficina principal" /></label><p className="text-xs text-amber-800">Captura manual: el comprobante se registra con advertencia para que Contabilidad coteje los datos contra el PDF antes de aprobarlo.</p><button disabled={busy || !societies.length} className="rounded-lg bg-brand-teal px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{busy ? 'Guardando…' : 'Registrar para revisión'}</button></form>}
    </section>

    {batch.length > 0 && <section className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="font-semibold text-brand-navy">Resultado del lote</h2><div className="mt-3 space-y-2">{batch.map((row, index) => <div key={`${row.archivo}-${index}`} className={`rounded-lg p-3 text-sm ${row.estado === 'error' ? 'bg-red-50 text-red-800' : row.estado === 'aviso' || row.advertencias?.length ? 'bg-amber-50 text-amber-900' : 'bg-emerald-50 text-emerald-900'}`}><strong>{row.archivo}</strong> · {row.estado === 'registrada' ? `${row.factura?.numero} · ${row.factura?.proveedor_razon_social} · ${row.factura ? money(row.factura.monto_total, row.factura.moneda) : ''}` : row.detalle}<ul className="mt-1 list-inside list-disc">{row.advertencias?.map(w => <li key={w}>{w}</li>)}</ul></div>)}</div></section>}

    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 p-5"><div><h2 className="text-lg font-semibold text-brand-navy">Bandeja sin pedido</h2><p className="mt-1 text-sm text-slate-500">{items.length} comprobantes visibles · cada sociedad se consulta según tus permisos.</p></div><div className="flex flex-wrap gap-2"><input className="rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="RUC, razón social o número" value={search} onChange={e => setSearch(e.target.value)} /><select className="rounded-lg border border-slate-300 px-3 py-2 text-sm" value={filterSociety} onChange={e => setFilterSociety(e.target.value)}><option value="">Todas las sociedades</option>{societies.map(s => <option key={s.id} value={s.id}>{s.razon_social}</option>)}</select><select className="rounded-lg border border-slate-300 px-3 py-2 text-sm" value={status} onChange={e => setStatus(e.target.value)}><option value="todas">Todos los estados</option><option>Pendiente de revisión</option><option>Aprobada para integración SAP</option><option>Rechazada</option></select></div></div>
      {loading ? <p className="p-8 text-slate-500">Cargando…</p> : items.length === 0 ? <div className="p-10 text-center"><p className="font-semibold text-brand-navy">Aún no hay facturas sin OC/OS</p><p className="mt-1 text-sm text-slate-500">Carga un lote XML o registra un recibo PDF manual.</p></div> : <div className="overflow-x-auto"><table className="w-full min-w-[900px] text-left text-sm"><thead className="bg-brand-soft text-brand-navy"><tr><th className="px-4 py-3">Comprobante / proveedor</th><th className="px-4 py-3">Emisión</th><th className="px-4 py-3">Categoría</th><th className="px-4 py-3">Total</th><th className="px-4 py-3">Archivos</th><th className="px-4 py-3">Estado</th><th className="px-4 py-3">Acciones</th></tr></thead><tbody>{items.map(invoice => <tr key={invoice.id} className="border-t border-slate-100 align-top"><td className="px-4 py-3"><button onClick={() => selectInvoice(invoice)} className="font-semibold text-brand-teal hover:underline">{invoice.numero}</button><span className="block text-slate-700">{invoice.proveedor_razon_social}</span><span className="text-xs text-slate-500">RUC {invoice.proveedor_ruc}</span></td><td className="px-4 py-3">{new Date(`${invoice.fecha_emision}T12:00:00`).toLocaleDateString('es-PE')}</td><td className="px-4 py-3">{invoice.categoria}<span className="block text-xs text-slate-500">{invoice.origen === 'xml' ? 'Leído del XML' : 'Captura manual'}</span></td><td className="px-4 py-3 font-semibold">{money(invoice.monto_total, invoice.moneda)}</td><td className="px-4 py-3">{invoice.tiene_xml ? <button className="mr-2 text-brand-teal underline" onClick={() => openFile(invoice, 'xml')}>XML</button> : null}{invoice.tiene_pdf ? <button className="text-brand-teal underline" onClick={() => openFile(invoice, 'pdf')}>PDF</button> : <span className="text-amber-700">PDF pendiente</span>}</td><td className="px-4 py-3">{invoice.estado}</td><td className="px-4 py-3"><div className="flex flex-col items-start gap-2">{invoice.estado === 'Pendiente de revisión' && <><button disabled={busy} onClick={() => action(invoice, 'aprobar')} className="font-semibold text-emerald-700 disabled:opacity-50">Aprobar revisión</button><button disabled={busy} onClick={() => action(invoice, 'rechazar')} className="font-semibold text-red-700 disabled:opacity-50">Rechazar</button></>}{invoice.estado !== 'Pendiente de revisión' && <button onClick={() => selectInvoice(invoice)} className="font-semibold text-brand-teal">Consultar</button>}</div></td></tr>)}</tbody></table></div>}
    </section>

    {selected && <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4" role="presentation" onClick={e => { if (e.target === e.currentTarget) setSelected(null) }}><section role="dialog" aria-modal="true" aria-labelledby="detail-title" className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl"><div className="flex items-start justify-between gap-4"><div><p className="text-sm font-semibold text-brand-teal">Expediente sin OC/OS</p><h2 id="detail-title" className="mt-1 text-2xl font-bold text-brand-navy">{selected.numero}</h2><p className="mt-1 text-slate-600">{selected.proveedor_razon_social} · RUC {selected.proveedor_ruc}</p></div><button onClick={() => setSelected(null)} className="rounded-lg border px-3 py-1.5 text-sm">Cerrar</button></div><dl className="mt-5 grid gap-3 sm:grid-cols-2">{[['Estado', selected.estado], ['Sociedad receptora', societies.find(s => s.id === selected.sociedad_id)?.razon_social || selected.sociedad_id], ['Fecha de emisión', selected.fecha_emision], ['Categoría', selected.categoria], ['Periodo de servicio', selected.periodo_servicio || '—'], ['Centro de costo', selected.centro_costo || 'Pendiente de asignación'], ['Cuenta contable', selected.cuenta_contable || 'Pendiente de asignación'], ['Moneda', selected.moneda], ['Total', money(selected.monto_total, selected.moneda)], ['Subtotal', money(selected.monto_subtotal, selected.moneda)], ['IGV / impuestos', money(selected.monto_igv, selected.moneda)], ['Origen', selected.origen === 'xml' ? 'XML' : 'Captura manual'], ['Referencia', selected.observacion || 'Sin observaciones']].map(([label, value]) => <div key={label} className="rounded-lg bg-slate-50 p-3"><dt className="text-xs font-semibold uppercase text-slate-500">{label}</dt><dd className="mt-1 break-words text-sm text-slate-800">{value}</dd></div>)}</dl><div className="mt-5 flex gap-3">{selected.tiene_xml && <button onClick={() => openFile(selected, 'xml')} className="rounded-lg border border-brand-teal px-4 py-2 text-sm font-semibold text-brand-teal">Abrir XML</button>}{selected.tiene_pdf && <button onClick={() => openFile(selected, 'pdf')} className="rounded-lg border border-brand-teal px-4 py-2 text-sm font-semibold text-brand-teal">Ver PDF</button>}</div>{selected.estado === 'Pendiente de revisión' && <div className="mt-6 flex flex-wrap justify-end gap-3 border-t pt-4"><button onClick={() => action(selected, 'rechazar')} className="rounded-lg border border-red-300 px-4 py-2 font-semibold text-red-700">Rechazar con motivo</button><button onClick={() => action(selected, 'aprobar')} className="rounded-lg bg-brand-teal px-4 py-2 font-semibold text-white">Aprobar revisión</button></div>}</section></div>}
    {filePreview && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4" role="presentation" onClick={e => { if (e.target === e.currentTarget) { URL.revokeObjectURL(filePreview.url); setFilePreview(null) } }}><section role="dialog" aria-modal="true" aria-label={`Vista previa de ${filePreview.name}`} className="flex h-[90vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl"><div className="flex items-center justify-between border-b px-4 py-3"><strong className="truncate text-sm text-brand-navy">{filePreview.name}</strong><button onClick={() => { URL.revokeObjectURL(filePreview.url); setFilePreview(null) }} className="rounded-lg border px-3 py-1.5 text-sm">Cerrar vista previa</button></div><iframe title={filePreview.name} src={filePreview.url} className="min-h-0 flex-1 bg-slate-100" /></section></div>}
  </div>
}
