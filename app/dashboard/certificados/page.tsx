'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'

type Certificado = {
  id: string
  ruc_emisor: string
  sociedad: string | null
  numero: string
  fecha_emision: string
  fecha_pago: string | null
  moneda: string
  base_retencion: number
  tasa_retencion: number | null
  importe_retencion: number
  referencia_pago: string | null
  documento_sap: string | null
  facturas_relacionadas: { tipo: string; serie: string; numero: string; fecha_emision: string; importe: number; moneda: string }[]
  estado_sunat: 'pendiente' | 'aceptado' | 'rechazado' | 'anulado'
  motivo_estado: string | null
  archivos: { xml: boolean; pdf: boolean; cdr: boolean }
}

const api = 'http://localhost:8000'
const moneda = (amount: number, currency: string) => new Intl.NumberFormat('es-PE', { style: 'currency', currency }).format(amount)
const fecha = (value: string | null) => value ? new Intl.DateTimeFormat('es-PE').format(new Date(`${value}T00:00:00`)) : '—'
const etiquetaEstado: Record<Certificado['estado_sunat'], string> = {
  pendiente: 'Pendiente SUNAT', aceptado: 'Aceptado por SUNAT', rechazado: 'Rechazado', anulado: 'Anulado',
}

export default function Certificados() {
  const [certificados, setCertificados] = useState<Certificado[]>([])
  const [total, setTotal] = useState(0)
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [estado, setEstado] = useState('')
  const [sociedad, setSociedad] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [descargando, setDescargando] = useState('')

  const cargar = useCallback(async (signal?: AbortSignal, offset = 0, append = false) => {
    setCargando(true)
    setError('')
    try {
      const token = localStorage.getItem('access_token')
      const query = new URLSearchParams()
      if (desde) query.set('desde', desde)
      if (hasta) query.set('hasta', hasta)
      if (estado) query.set('estado', estado)
      if (sociedad) query.set('sociedad', sociedad)
      query.set('limit', '100')
      query.set('offset', String(offset))
      const response = await fetch(`${api}/retenciones?${query}`, { headers: { Authorization: `Bearer ${token || ''}` }, signal })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'No se pudieron cargar los certificados.')
      setCertificados(previous => append ? [...previous, ...(data.items || [])] : data.items || [])
      setTotal(data.total || 0)
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : 'No se pudieron cargar los certificados.')
    } finally {
      if (!signal?.aborted) setCargando(false)
    }
  }, [desde, hasta, estado, sociedad])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => void cargar(controller.signal), 0)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [cargar])

  const visibles = useMemo(() => {
    const term = busqueda.trim().toLocaleLowerCase('es-PE')
    if (!term) return certificados
    return certificados.filter(item => `${item.numero} ${item.ruc_emisor} ${item.referencia_pago || ''} ${item.documento_sap || ''} ${item.facturas_relacionadas.map(f => `${f.serie}-${f.numero}`).join(' ')}`.toLocaleLowerCase('es-PE').includes(term))
  }, [certificados, busqueda])

  async function descargar(item: Certificado, tipo: 'pdf' | 'xml' | 'cdr') {
    setDescargando(`${item.id}:${tipo}`)
    setError('')
    try {
      const response = await fetch(`${api}/retenciones/${item.id}/archivos/${tipo}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || 'No se pudo descargar el archivo.')
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${item.numero}-${tipo.toUpperCase()}.${tipo}`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo descargar el archivo.')
    } finally {
      setDescargando('')
    }
  }

  const aceptados = certificados.filter(item => item.estado_sunat === 'aceptado').length
  const importe = certificados.filter(item => item.estado_sunat === 'aceptado').reduce((sum, item) => sum + item.importe_retencion, 0)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-brand-navy">Certificados de retención</h1>
          <p className="mt-2 text-brand-muted">Consulta las retenciones comunicadas por tus clientes y descarga el CRE emitido por SUNAT.</p>
        </div>
        <button onClick={() => void cargar()} className="rounded-xl border border-brand-teal bg-white px-5 py-3 font-medium text-brand-teal hover:bg-brand-soft disabled:opacity-60" disabled={cargando}>
          {cargando ? 'Actualizando…' : 'Actualizar'}
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 border-l-4 border-l-brand-teal bg-white p-5"><p className="text-sm text-brand-muted">Certificados recibidos</p><p className="mt-2 text-3xl font-bold text-brand-navy">{total}</p></div>
        <div className="rounded-2xl border border-slate-200 border-l-4 border-l-emerald-600 bg-white p-5"><p className="text-sm text-brand-muted">Aceptados por SUNAT</p><p className="mt-2 text-3xl font-bold text-brand-navy">{aceptados}</p></div>
        <div className="rounded-2xl border border-slate-200 border-l-4 border-l-brand-teal bg-white p-5"><p className="text-sm text-brand-muted">Retención aceptada</p><p className="mt-2 text-3xl font-bold text-brand-navy">{moneda(importe, 'PEN')}</p></div>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <label className="text-sm font-semibold text-brand-navy">Buscar certificado o pago
            <input value={busqueda} onChange={event => setBusqueda(event.target.value)} placeholder="Serie, número o referencia" className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal outline-none focus:border-brand-teal focus:ring-2 focus:ring-brand-teal/20" />
          </label>
          <label className="text-sm font-semibold text-brand-navy">Estado SUNAT
            <select value={estado} onChange={event => setEstado(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 font-normal outline-none focus:border-brand-teal">
              <option value="">Todos los estados</option><option value="aceptado">Aceptado</option><option value="pendiente">Pendiente</option><option value="rechazado">Rechazado</option><option value="anulado">Anulado</option>
            </select>
          </label>
          <label className="text-sm font-semibold text-brand-navy">Desde
            <input type="date" value={desde} onChange={event => setDesde(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal outline-none focus:border-brand-teal" />
          </label>
          <label className="text-sm font-semibold text-brand-navy">Hasta
            <input type="date" value={hasta} onChange={event => setHasta(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal outline-none focus:border-brand-teal" />
          </label>
          <label className="text-sm font-semibold text-brand-navy">RUC de la sociedad
            <input inputMode="numeric" maxLength={11} value={sociedad} onChange={event => setSociedad(event.target.value.replace(/\D/g, ''))} placeholder="Todas las sociedades" className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal outline-none focus:border-brand-teal" />
          </label>
        </div>
        {(desde || hasta || estado || sociedad || busqueda) && <button onClick={() => { setDesde(''); setHasta(''); setEstado(''); setSociedad(''); setBusqueda('') }} className="mt-4 text-sm font-semibold text-brand-teal hover:underline">Limpiar filtros</button>}
      </section>

      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">{error}</div>}
      {cargando ? <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-brand-muted">Cargando certificados…</div> : visibles.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 border-l-4 border-l-brand-teal bg-white p-8">
          <h2 className="text-lg font-semibold text-brand-navy">{total === 0 ? 'Aún no hay certificados de retención' : 'No encontramos coincidencias'}</h2>
          <p className="mt-2 text-brand-muted">{total === 0 ? 'Cuando tu cliente emita y publique un comprobante de retención, podrás consultar aquí sus datos y descargar el PDF, XML y CDR.' : 'Prueba con otro número, estado o rango de fechas.'}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {visibles.map(item => (
            <article key={item.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="text-xl font-bold text-brand-navy">{item.numero}</h2>
                    <span className={`rounded-full px-3 py-1 text-sm font-semibold ${item.estado_sunat === 'aceptado' ? 'bg-emerald-50 text-emerald-800' : item.estado_sunat === 'rechazado' || item.estado_sunat === 'anulado' ? 'bg-red-50 text-red-800' : 'bg-amber-50 text-amber-800'}`}>{etiquetaEstado[item.estado_sunat]}</span>
                  </div>
                  <p className="mt-2 text-sm text-brand-muted">Emitido por RUC {item.ruc_emisor}{item.sociedad ? ` · Sociedad SAP ${item.sociedad}` : ''} · {fecha(item.fecha_emision)}</p>
                </div>
                <div className="text-left sm:text-right"><p className="text-sm text-brand-muted">Importe retenido</p><p className="text-2xl font-bold text-brand-navy">{moneda(item.importe_retencion, item.moneda)}</p></div>
              </div>
              <dl className="mt-5 grid gap-4 border-t border-slate-100 pt-4 sm:grid-cols-2 lg:grid-cols-4">
                <div><dt className="text-xs font-semibold uppercase tracking-wide text-brand-muted">Base de retención</dt><dd className="mt-1 font-medium text-brand-navy">{moneda(item.base_retencion, item.moneda)}</dd></div>
                <div><dt className="text-xs font-semibold uppercase tracking-wide text-brand-muted">Tasa</dt><dd className="mt-1 font-medium text-brand-navy">{item.tasa_retencion == null ? '—' : `${item.tasa_retencion}%`}</dd></div>
                <div><dt className="text-xs font-semibold uppercase tracking-wide text-brand-muted">Pago relacionado</dt><dd className="mt-1 font-medium text-brand-navy">{item.referencia_pago || item.documento_sap || '—'}{item.fecha_pago ? ` · ${fecha(item.fecha_pago)}` : ''}</dd></div>
                <div><dt className="text-xs font-semibold uppercase tracking-wide text-brand-muted">Facturas relacionadas</dt><dd className="mt-1 font-medium text-brand-navy">{item.facturas_relacionadas.length ? item.facturas_relacionadas.map(invoice => `${invoice.serie}-${invoice.numero}`).join(', ') : 'Ver XML del certificado'}</dd></div>
              </dl>
              {item.motivo_estado && <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{item.motivo_estado}</p>}
              <div className="mt-5 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                {(['pdf', 'xml', 'cdr'] as const).filter(type => item.archivos[type]).map(type => <button key={type} onClick={() => void descargar(item, type)} disabled={item.estado_sunat !== 'aceptado' || descargando === `${item.id}:${type}`} className="rounded-lg border border-brand-teal px-4 py-2 text-sm font-semibold text-brand-teal hover:bg-brand-soft disabled:cursor-not-allowed disabled:opacity-50">{descargando === `${item.id}:${type}` ? 'Descargando…' : `Descargar ${type.toUpperCase()}`}</button>)}
                {item.estado_sunat !== 'aceptado' && <span className="self-center text-sm text-brand-muted">La descarga estará disponible cuando SUNAT confirme la aceptación.</span>}
              </div>
            </article>
          ))}
          <p className="text-sm text-brand-muted">Mostrando {visibles.length} de {total} certificados</p>
          {certificados.length < total && <button onClick={() => void cargar(undefined, certificados.length, true)} disabled={cargando} className="rounded-lg border border-brand-teal px-4 py-2 text-sm font-semibold text-brand-teal hover:bg-brand-soft disabled:opacity-50">{cargando ? 'Cargando…' : 'Cargar más'}</button>}
        </div>
      )}
    </div>
  )
}
