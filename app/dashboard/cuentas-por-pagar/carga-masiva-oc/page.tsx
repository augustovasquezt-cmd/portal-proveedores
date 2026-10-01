'use client'

import { ChangeEvent, useState } from 'react'

const API = '/api-backend/cuentas-por-pagar/carga-masiva-oc'
type Outcome = {
  clave_factura?: string; estado: 'validada' | 'registrada' | 'error' | 'aviso'; detalle?: string
  id?: string | null; numero?: string; proveedor?: string; total?: string; pedidos?: string[]; posiciones?: number; documentos?: string[]; archivo?: string
}
type BatchResult = { modo: string; validas: number; registradas: number; errores: number; total: number; items: Outcome[] }

export default function CargaMasivaFacturasOcPage() {
  const [excel, setExcel] = useState<File | null>(null)
  const [xmlFiles, setXmlFiles] = useState<File[]>([])
  const [pdfFiles, setPdfFiles] = useState<File[]>([])
  const [result, setResult] = useState<BatchResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const inputClass = 'mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-brand-teal focus:ring-2 focus:ring-brand-teal/20'
  const tokenHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` })

  function onExcelChange(event: ChangeEvent<HTMLInputElement>) {
    setExcel(event.target.files?.[0] || null)
    setResult(null); setError(''); setNotice('')
  }

  async function downloadTemplate() {
    setBusy(true); setError('')
    try {
      const response = await fetch(`${API}/plantilla.xlsx`, { headers: tokenHeaders() })
      if (!response.ok) throw new Error(await errorMessage(response))
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a'); link.href = url; link.download = 'plantilla_facturas_con_oc.xlsx'; link.click()
      URL.revokeObjectURL(url)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo descargar la plantilla.') }
    finally { setBusy(false) }
  }

  async function errorMessage(response: Response) {
    try { const body = await response.json(); return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body) }
    catch { return `Error HTTP ${response.status}` }
  }

  function makeForm() {
    if (!excel) throw new Error('Selecciona el archivo Excel .xlsx.')
    if (!pdfFiles.length) throw new Error('Adjunta los PDF de las facturas; se requiere uno por cada factura.')
    const form = new FormData()
    form.append('excel', excel)
    xmlFiles.forEach(file => form.append('xml_files', file))
    pdfFiles.forEach(file => form.append('pdf_files', file))
    return form
  }

  async function run(mode: 'validar' | 'registrar') {
    setBusy(true); setError(''); setNotice('')
    try {
      const response = await fetch(`${API}/${mode}`, { method: 'POST', headers: tokenHeaders(), body: makeForm() })
      if (!response.ok) throw new Error(await errorMessage(response))
      const data: BatchResult = await response.json()
      setResult(data)
      if (mode === 'validar') setNotice(`Validación finalizada: ${data.validas} facturas listas y ${data.errores} con observaciones.`)
      else setNotice(`Carga finalizada: ${data.registradas} facturas registradas para revisión. No se enviaron ni contabilizaron en SAP.`)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo procesar el lote.') }
    finally { setBusy(false) }
  }

  const readyToImport = Boolean(result && result.modo === 'validacion' && result.validas > 0 && result.errores === 0)
  const money = (value?: string) => value ? new Intl.NumberFormat('es-PE', { style: 'currency', currency: 'PEN' }).format(Number(value)) : '—'

  return <div className="mx-auto max-w-7xl space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-sm font-semibold uppercase tracking-wide text-brand-teal">Cuentas por pagar · Recepción interna</p><h1 className="mt-1 text-3xl font-bold text-brand-navy">Carga masiva de facturas con OC/OS</h1><p className="mt-2 max-w-3xl text-slate-600">Carga un Excel con facturas y posiciones, valida sus saldos contra SAP y registra el lote para revisión contable.</p></div>
      <button type="button" onClick={() => void downloadTemplate()} disabled={busy} className="rounded-lg border border-brand-teal px-4 py-2.5 font-semibold text-brand-teal hover:bg-brand-soft disabled:opacity-50">Descargar plantilla Excel</button>
    </header>

    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-brand-navy">Cómo preparar el archivo</h2>
      <ol className="mt-3 grid gap-3 text-sm text-slate-600 md:grid-cols-2">
        <li className="rounded-lg bg-slate-50 p-3"><strong className="text-brand-navy">Facturas:</strong> una fila por comprobante, con clave, proveedor, sociedad, serie, correlativo, fecha e importes.</li>
        <li className="rounded-lg bg-slate-50 p-3"><strong className="text-brand-navy">Posiciones:</strong> una fila por posición facturada. Puedes combinar varias posiciones y pedidos de un mismo proveedor y sociedad.</li>
        <li className="rounded-lg bg-slate-50 p-3">El sistema toma el precio de la orden y valida cantidades, saldos pendientes, proveedor, sociedad y duplicados.</li>
        <li className="rounded-lg bg-slate-50 p-3">El PDF es obligatorio. El XML es opcional; si lo adjuntas, cada fila debe indicar su <code>linea_xml</code> para contrastar cantidades e importes.</li>
      </ol>
      <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Las facturas se guardan como <strong>Pendiente de revisión</strong>. Esta herramienta no las contabiliza ni las envía a SAP.</p>
    </section>

    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-brand-navy">Archivos del lote</h2>
      <div className="mt-4 grid gap-4">
        <label className="block text-sm font-semibold text-slate-700">Libro Excel .xlsx (máximo 2 MB)<input required className={inputClass} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={onExcelChange} /></label>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm font-semibold text-slate-700">PDF de cada factura · obligatorio · hasta 100 archivos, 5 MB cada uno<input className={inputClass} type="file" accept=".pdf,application/pdf" multiple onChange={event => { setPdfFiles(Array.from(event.target.files || [])); setResult(null) }} /></label>
          <label className="block text-sm font-semibold text-slate-700">XML UBL · opcional · hasta 100 archivos, 5 MB cada uno<input className={inputClass} type="file" accept=".xml,application/xml,text/xml" multiple onChange={event => { setXmlFiles(Array.from(event.target.files || [])); setResult(null) }} /></label>
        </div>
        <p className="text-xs text-slate-500">Los nombres deben coincidir exactamente con <code>archivo_pdf</code> y <code>archivo_xml</code> del Excel. Límite total de adjuntos: 30 MB.</p>
        <div className="flex flex-wrap gap-3">
          <button type="button" onClick={() => void run('validar')} disabled={busy || !excel || !pdfFiles.length} className="rounded-lg border border-brand-teal px-4 py-2.5 font-semibold text-brand-teal disabled:cursor-not-allowed disabled:opacity-50">{busy ? 'Procesando…' : 'Validar lote'}</button>
          <button type="button" onClick={() => void run('registrar')} disabled={busy || !readyToImport} className="rounded-lg bg-brand-teal px-4 py-2.5 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">Registrar facturas válidas</button>
        </div>
      </div>
    </section>

    {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{error}</div>}
    {notice && <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-emerald-900">{notice}</div>}
    {result && <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-5"><div><h2 className="text-lg font-semibold text-brand-navy">Resultado del lote</h2><p className="mt-1 text-sm text-slate-500">{result.total} facturas · {result.validas} listas · {result.errores} con error</p></div>{result.modo === 'validacion' && result.errores > 0 && <p className="text-sm font-medium text-amber-800">Corrige el Excel o los adjuntos y vuelve a validar.</p>}</div>
      <div className="overflow-x-auto"><table className="w-full min-w-[850px] text-left text-sm"><thead className="bg-brand-soft text-brand-navy"><tr>{['Clave / factura','Proveedor','Pedido(s) y posiciones','Importe','Estado','Detalle'].map(label => <th key={label} className="px-4 py-3 font-semibold">{label}</th>)}</tr></thead><tbody>{result.items.map((item, index) => <tr key={`${item.clave_factura || item.archivo}-${index}`} className="border-t border-slate-100 align-top"><td className="px-4 py-3"><strong>{item.clave_factura || item.archivo || 'Adjunto'}</strong>{item.numero && <span className="mt-1 block text-slate-500">{item.numero}</span>}</td><td className="px-4 py-3">{item.proveedor || '—'}</td><td className="px-4 py-3">{item.pedidos?.join(', ') || '—'}{item.posiciones !== undefined && <span className="block text-xs text-slate-500">{item.posiciones} posiciones</span>}</td><td className="px-4 py-3 font-semibold">{money(item.total)}</td><td className="px-4 py-3"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${item.estado === 'error' ? 'bg-red-100 text-red-800' : item.estado === 'registrada' ? 'bg-emerald-100 text-emerald-800' : 'bg-sky-100 text-sky-800'}`}>{item.estado}</span></td><td className="max-w-sm px-4 py-3 text-slate-600">{item.detalle || (item.documentos?.length ? `Adjuntos: ${item.documentos.join(', ')}` : 'Validación correcta.')}</td></tr>)}</tbody></table></div>
    </section>}
  </div>
}
