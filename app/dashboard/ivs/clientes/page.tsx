'use client'

import { FormEvent, useCallback, useEffect, useState } from 'react'

type Quota = { usados: number; maximo: number }
type Client = { id: string; codigo: string; nombre: string; activo: boolean; sociedad_principal: { id:string; ruc:string; razon_social:string } | null; cupos: { administradores: Quota; cuentas_por_pagar: Quota; proveedores: Quota; sociedades: Quota } }
const api = 'http://localhost:8000'
const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`, 'Content-Type': 'application/json' })

function readableApiError(detail: unknown, fallback: string) {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const fieldNames: Record<string, string> = {
      codigo: 'Código', nombre: 'Nombre', ruc_principal: 'RUC principal',
      razon_social_principal: 'Razón social', max_administradores: 'Máximo de administradores',
      max_cuentas_por_pagar: 'Máximo de cuentas por pagar', max_proveedores: 'Máximo de proveedores',
      max_sociedades: 'Máximo de sociedades',
    }
    const messages = detail.map((item: unknown) => {
      if (!item || typeof item !== 'object') return ''
      const error = item as { loc?: unknown[]; msg?: unknown; type?: unknown }
      const field = error.loc?.filter(part => part !== 'body').map(part => fieldNames[String(part)] || String(part)).join(' · ')
      const message = error.type === 'missing' ? 'es obligatorio' : error.type === 'string_pattern_mismatch' ? 'tiene un formato no válido' : typeof error.msg === 'string' ? error.msg : 'contiene un valor no válido'
      return field ? `${field}: ${message}.` : `${message}.`
    }).filter(Boolean)
    if (messages.length) return messages.join(' ')
  }
  if (detail && typeof detail === 'object') {
    const error = detail as { message?: unknown; msg?: unknown }
    if (typeof error.message === 'string') return error.message
    if (typeof error.msg === 'string') return error.msg
  }
  return fallback
}

export default function ClientesIVS() {
  const [clients, setClients] = useState<Client[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [societies, setSocieties] = useState<{ id:string; ruc:string; razon_social:string; codigo_sap:string|null; es_principal:boolean; activo:boolean }[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [secret, setSecret] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ codigo:'', nombre:'', ruc_principal:'', razon_social_principal:'', codigo_sap_principal:'', max_administradores:1, max_cuentas_por_pagar:5, max_proveedores:50, max_sociedades:10 })
  const [clientForm, setClientForm] = useState({ codigo:'', nombre:'' })
  const [society, setSociety] = useState({ ruc:'', razon_social:'', codigo_sap:'' })
  const [admin, setAdmin] = useState({ usuario:'', nombre:'' })
  const [quotaForm, setQuotaForm] = useState({ max_administradores:1, max_cuentas_por_pagar:5, max_proveedores:50, max_sociedades:10 })
  const client = clients.find(item => item.id === selectedId)

  const load = useCallback(async () => {
    setError('')
    try {
      const response = await fetch(`${api}/ivs/clientes`, { headers: headers() }); const data = await response.json()
      if (!response.ok) throw new Error(readableApiError(data.detail, 'No se pudieron cargar los clientes.'))
      setClients(data); if (!selectedId && data.length) { setSelectedId(data[0].id); setClientForm({ codigo:data[0].codigo, nombre:data[0].nombre }) }
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudieron cargar los clientes.') }
  }, [selectedId])
  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer) }, [load])
  useEffect(() => {
    if (!selectedId) return
    void (async () => { const r = await fetch(`${api}/ivs/clientes/${selectedId}/sociedades`, { headers: headers() }); if (r.ok) setSocieties(await r.json()) })()
  }, [selectedId])

  async function call(path: string, method: string, body?: unknown) {
    setError(''); setNotice(''); setSecret(''); setBusy(true)
    try {
      const response = await fetch(`${api}${path}`, { method, headers: headers(), ...(body ? { body: JSON.stringify(body) } : {}) }); const data = await response.json()
      if (!response.ok) throw new Error(readableApiError(data.detail, 'La operación no se completó.'))
      if (data.token) setSecret(data.token)
      setNotice(data.mensaje || 'Cambios guardados.'); await load(); return data
    } catch (e) { setError(e instanceof Error ? e.message : 'La operación no se completó.'); return null }
    finally { setBusy(false) }
  }

  async function createClient(event: FormEvent) { event.preventDefault(); const data = await call('/ivs/clientes','POST',form); if (data) { setForm({ codigo:'', nombre:'', ruc_principal:'', razon_social_principal:'', codigo_sap_principal:'', max_administradores:1, max_cuentas_por_pagar:5, max_proveedores:50, max_sociedades:10 }); setSelectedId(data.id); setClientForm({codigo:data.codigo,nombre:data.nombre}); setQuotaForm({max_administradores:data.cupos.administradores.maximo,max_cuentas_por_pagar:data.cupos.cuentas_por_pagar.maximo,max_proveedores:data.cupos.proveedores.maximo,max_sociedades:data.cupos.sociedades.maximo}) } }
  async function updateClient(event: FormEvent) { event.preventDefault(); if (!client) return; await call(`/ivs/clientes/${client.id}`,'PATCH',clientForm) }
  async function updateQuotas(event: FormEvent) { event.preventDefault(); if (!client) return; await call(`/ivs/clientes/${client.id}/cupos`,'PATCH',quotaForm) }
  async function createSociety(event: FormEvent) { event.preventDefault(); if (!client) return; const data=await call(`/ivs/clientes/${client.id}/sociedades`,'POST',society); if(data){setSociety({ruc:'',razon_social:'',codigo_sap:''});const r=await fetch(`${api}/ivs/clientes/${client.id}/sociedades`,{headers:headers()});if(r.ok)setSocieties(await r.json())} }
  async function toggleSociety(item: {id:string; activo:boolean}) { if (!client) return; const data=await call(`/ivs/clientes/${client.id}/sociedades/${item.id}`,'PATCH',{activo:!item.activo}); if(data){const r=await fetch(`${api}/ivs/clientes/${client.id}/sociedades`,{headers:headers()});if(r.ok)setSocieties(await r.json())} }
  async function createAdmin(event: FormEvent) { event.preventDefault(); if (!client) return; const data=await call(`/ivs/clientes/${client.id}/administradores`,'POST',admin); if(data)setAdmin({usuario:'',nombre:''}) }

  return <div className="mx-auto max-w-6xl space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-3xl font-bold text-brand-navy">Administración IVS</h1><p className="mt-2 text-brand-muted">Gestiona clientes, sociedades receptoras y límites de suscripción.</p></div><button onClick={()=>void load()} className="rounded-lg border border-brand-teal px-4 py-2 font-semibold text-brand-teal">Actualizar</button></header>
    {error&&<p role="alert" className="rounded-xl bg-red-50 p-4 text-red-800">{error}</p>}{notice&&<p role="status" className="rounded-xl bg-emerald-50 p-4 text-emerald-900">{notice}</p>}{secret&&<div className="rounded-xl border border-amber-300 bg-amber-50 p-4"><p className="font-semibold">Credencial API SAP · solo se muestra ahora</p><code className="mt-2 block break-all select-all rounded bg-white p-3">{secret}</code><p className="mt-2 text-sm">Guárdala en un gestor de secretos y compártela con el consultor SAP del cliente.</p></div>}
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
      <form onSubmit={createClient} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold text-brand-navy">Crear cliente y su RUC principal</h2><p className="text-sm text-brand-muted">El cliente representa al grupo empresarial. Su primer RUC receptor queda como sociedad principal; podrás añadir otros después.</p><input required placeholder="Código único (ej. grupo-acme)" value={form.codigo} onChange={e=>setForm({...form,codigo:e.target.value})} className="w-full rounded-lg border p-2.5"/><input required placeholder="Nombre del cliente o grupo empresarial" value={form.nombre} onChange={e=>setForm({...form,nombre:e.target.value})} className="w-full rounded-lg border p-2.5"/><div className="grid gap-3 sm:grid-cols-2"><input required inputMode="numeric" pattern="\d{11}" maxLength={11} placeholder="RUC principal (11 dígitos)" value={form.ruc_principal} onChange={e=>setForm({...form,ruc_principal:e.target.value.replace(/\D/g,'')})} className="w-full rounded-lg border p-2.5"/><input required placeholder="Razón social del RUC principal" value={form.razon_social_principal} onChange={e=>setForm({...form,razon_social_principal:e.target.value})} className="w-full rounded-lg border p-2.5"/></div><input placeholder="Código de sociedad SAP (opcional)" value={form.codigo_sap_principal} onChange={e=>setForm({...form,codigo_sap_principal:e.target.value})} className="w-full rounded-lg border p-2.5"/><div className="grid grid-cols-2 gap-3">{([['max_administradores','Administradores'],['max_cuentas_por_pagar','Cuentas por pagar'],['max_proveedores','Proveedores'],['max_sociedades','Sociedades']] as const).map(([key,label])=><label key={key} className="text-sm">Máximo {label}<input required type="number" min={key==='max_administradores'||key==='max_sociedades'?1:0} value={form[key]} onChange={e=>setForm({...form,[key]:Number(e.target.value)})} className="mt-1 w-full rounded-lg border p-2"/></label>)}</div><button disabled={busy} className="rounded-lg bg-brand-teal px-4 py-2.5 font-semibold text-white">Crear cliente</button></form>
      <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold text-brand-navy">Clientes activos e inactivos</h2><select value={selectedId} onChange={e=>{const next=clients.find(c=>c.id===e.target.value);setSelectedId(e.target.value);if(next){setClientForm({codigo:next.codigo,nombre:next.nombre});setQuotaForm({max_administradores:next.cupos.administradores.maximo,max_cuentas_por_pagar:next.cupos.cuentas_por_pagar.maximo,max_proveedores:next.cupos.proveedores.maximo,max_sociedades:next.cupos.sociedades.maximo})}}} className="w-full rounded-lg border p-2.5"><option value="">Selecciona un cliente</option>{clients.map(c=><option key={c.id} value={c.id}>{c.nombre} ({c.codigo})</option>)}</select>{client&&<><p className="text-sm text-brand-muted">RUC principal: {client.sociedad_principal?.razon_social} · {client.sociedad_principal?.ruc}</p><div className="grid grid-cols-2 gap-3">{Object.entries(client.cupos).map(([label,q])=><div key={label} className="rounded-lg bg-slate-50 p-3"><p className="text-xs capitalize text-brand-muted">{label.replaceAll('_',' ')}</p><p className="font-bold text-brand-navy">{q.usados} / {q.maximo}</p></div>)}</div></>}</section>
    </div>
    {client&&<div className="grid gap-6 lg:grid-cols-2">
      <form onSubmit={updateClient} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold text-brand-navy">Editar cliente</h2><label className="block text-sm">Código<input required pattern="[a-z0-9][a-z0-9-]{2,59}" value={clientForm.codigo} onChange={e=>setClientForm({...clientForm,codigo:e.target.value})} className="mt-1 w-full rounded-lg border p-2.5"/></label><label className="block text-sm">Nombre del cliente o grupo<input required minLength={2} maxLength={200} value={clientForm.nombre} onChange={e=>setClientForm({...clientForm,nombre:e.target.value})} className="mt-1 w-full rounded-lg border p-2.5"/></label><button disabled={busy} className="rounded-lg border border-brand-teal px-4 py-2 font-semibold text-brand-teal">Guardar datos del cliente</button></form>
      <form onSubmit={updateQuotas} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold text-brand-navy">Editar cupos · {client.nombre}</h2><p className="text-sm text-brand-muted">Puedes aumentar o reducir los límites contratados. No se permite bajarlos por debajo de las cuentas activas.</p><div className="grid grid-cols-2 gap-3">{([['max_administradores','Administradores'],['max_cuentas_por_pagar','Cuentas por pagar'],['max_proveedores','Proveedores'],['max_sociedades','Sociedades']] as const).map(([key,label])=><label key={key} className="text-sm">Máximo {label}<input required type="number" min={key==='max_administradores'||key==='max_sociedades'?1:0} value={quotaForm[key]} onChange={e=>setQuotaForm({...quotaForm,[key]:Number(e.target.value)})} className="mt-1 w-full rounded-lg border p-2"/></label>)}</div><button disabled={busy} className="rounded-lg border border-brand-teal px-4 py-2 font-semibold text-brand-teal">Guardar cupos</button><button type="button" disabled={busy} onClick={()=>void call(`/ivs/clientes/${client.id}/credenciales-sap`,'POST')} className="ml-2 rounded-lg border border-slate-300 px-4 py-2 font-semibold">Rotar clave SAP</button></form>
      <form onSubmit={createAdmin} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold text-brand-navy">Crear administrador del cliente</h2><input required type="email" placeholder="Correo" value={admin.usuario} onChange={e=>setAdmin({...admin,usuario:e.target.value})} className="w-full rounded-lg border p-2.5"/><input required placeholder="Nombre completo" value={admin.nombre} onChange={e=>setAdmin({...admin,nombre:e.target.value})} className="w-full rounded-lg border p-2.5"/><button disabled={busy} className="rounded-lg bg-brand-teal px-4 py-2.5 font-semibold text-white">Crear y mostrar clave temporal</button></form>
      <form onSubmit={createSociety} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold text-brand-navy">Agregar otra sociedad del grupo</h2><p className="text-sm text-brand-muted">Registra el RUC receptor, la razón social legal y su código de sociedad SAP si aplica. El RUC principal no se puede desactivar.</p><input required inputMode="numeric" pattern="\d{11}" maxLength={11} placeholder="RUC de 11 dígitos" value={society.ruc} onChange={e=>setSociety({...society,ruc:e.target.value.replace(/\D/g,'')})} className="w-full rounded-lg border p-2.5"/><input required placeholder="Razón social" value={society.razon_social} onChange={e=>setSociety({...society,razon_social:e.target.value})} className="w-full rounded-lg border p-2.5"/><input placeholder="Código de sociedad SAP" value={society.codigo_sap} onChange={e=>setSociety({...society,codigo_sap:e.target.value})} className="w-full rounded-lg border p-2.5"/><button disabled={busy} className="rounded-lg bg-brand-teal px-4 py-2.5 font-semibold text-white">Agregar sociedad</button><ul className="space-y-2 text-sm">{societies.map(s=><li key={s.id} className="flex items-center justify-between gap-2 border-t pt-2"><span>{s.es_principal?'Principal · ':''}{s.razon_social} · RUC {s.ruc} {s.codigo_sap?`· SAP ${s.codigo_sap}`:''} · {s.activo?'Activa':'Inactiva'}</span>{!s.es_principal&&<button type="button" disabled={busy} onClick={()=>void toggleSociety(s)} className="shrink-0 font-semibold text-brand-teal">{s.activo?'Desactivar':'Reactivar'}</button>}</li>)}</ul></form>
    </div>}
  </div>
}
