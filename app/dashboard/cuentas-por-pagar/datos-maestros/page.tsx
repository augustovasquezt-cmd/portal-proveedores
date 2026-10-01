'use client'

import { useEffect, useState } from 'react'

type MasterData = { proveedores: { id: string; ruc: string; razon_social: string; email: string; estado: string; activo: boolean }[]; sociedades: { ruc: string; razon_social: string; codigo_sap?: string }[] }

export default function DatosMaestrosPage() {
  const [data, setData] = useState<MasterData | null>(null)
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => fetch('http://localhost:8000/cuentas-por-pagar/datos-maestros', { headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` } })
      .then(async response => { if (!response.ok) throw new Error('No se pudieron cargar los datos maestros.'); setData(await response.json()) })
      .catch(caught => setError(caught instanceof Error ? caught.message : 'Error al consultar los datos maestros.')), 0)
    return () => window.clearTimeout(timer)
  }, [])

  const term = search.trim().toLocaleLowerCase()
  const providers = (data?.proveedores || []).filter(p => !term || `${p.ruc} ${p.razon_social} ${p.email}`.toLocaleLowerCase().includes(term))
  return <div className="mx-auto max-w-7xl space-y-6">
    <header><p className="text-sm font-semibold uppercase tracking-wide text-brand-teal">Consulta</p><h1 className="mt-1 text-3xl font-bold text-brand-navy">Datos maestros</h1><p className="mt-2 text-slate-600">Proveedores registrados y sociedades receptoras disponibles para el portal.</p></header>
    {error && <div role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">{error}</div>}
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-200 p-5"><div><h2 className="font-semibold text-brand-navy">Sociedades receptoras</h2><p className="mt-1 text-sm text-slate-500">Entidades habilitadas para recibir comprobantes.</p></div><span className="text-sm text-slate-500">{data?.sociedades.length ?? '—'} sociedades</span></div><div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3">{(data?.sociedades || []).map(company => <article key={company.ruc} className="rounded-lg border border-slate-200 p-4"><h3 className="font-semibold text-brand-navy">{company.razon_social || 'Sociedad receptora'}</h3><p className="mt-1 text-sm text-slate-600">RUC {company.ruc}</p>{company.codigo_sap && <p className="mt-1 text-xs text-slate-500">Código SAP: {company.codigo_sap}</p>}</article>)}{data && data.sociedades.length === 0 && <p className="text-sm text-slate-500">Aún no se han configurado sociedades receptoras.</p>}</div></section>
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-200 p-5"><div><h2 className="font-semibold text-brand-navy">Maestro de proveedores</h2><p className="mt-1 text-sm text-slate-500">Consulta el RUC y los datos de contacto de cada proveedor.</p></div><label className="text-sm font-medium text-brand-navy">Buscar<input value={search} onChange={e => setSearch(e.target.value)} placeholder="RUC, razón social o correo" className="mt-1 block w-full min-w-64 rounded-lg border border-slate-300 px-3 py-2 font-normal" /></label></div>{!data ? <p className="p-5 text-slate-500">Cargando datos…</p> : providers.length === 0 ? <p className="p-8 text-center text-slate-500">No hay proveedores que coincidan.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-sm"><thead className="bg-brand-soft text-left text-brand-navy"><tr>{['RUC','Razón social','Correo','Estado','Acceso'].map(x => <th key={x} className="px-5 py-3">{x}</th>)}</tr></thead><tbody>{providers.map(provider => <tr key={provider.id} className="border-t border-slate-100"><td className="px-5 py-3">{provider.ruc}</td><td className="px-5 py-3 font-medium">{provider.razon_social}</td><td className="px-5 py-3">{provider.email}</td><td className="px-5 py-3">{provider.estado}</td><td className="px-5 py-3">{provider.activo ? 'Activo' : 'Desactivado'}</td></tr>)}</tbody></table></div>}</section>
  </div>
}
