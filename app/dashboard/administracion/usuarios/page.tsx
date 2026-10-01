'use client'

import { FormEvent, useCallback, useEffect, useState } from 'react'

type Interno = { id: string; usuario: string; nombre: string; rol: string; activo: boolean; debe_cambiar_password: boolean; administrable: boolean; sociedades_ids: string[] }
type Proveedor = { id: string; ruc: string; razon_social: string; email: string; estado: string; activo: boolean; debe_cambiar_password: boolean; sociedades_ids: string[] }
type Usuarios = { usuarios_internos: Interno[]; proveedores: Proveedor[] }
type Sociedad = { id: string; ruc: string; razon_social: string; codigo_sap: string | null }
type Cuotas = { administradores: { usados: number; maximo: number }; cuentas_por_pagar: { usados: number; maximo: number }; proveedores: { usados: number; maximo: number }; sociedades: { usados: number; maximo: number } }
const api = 'http://localhost:8000'
const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`, 'Content-Type': 'application/json' })

export default function AdministrarUsuarios() {
  const [data, setData] = useState<Usuarios>({ usuarios_internos: [], proveedores: [] })
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')
  const [passwordTemporal, setPasswordTemporal] = useState('')
  const [busy, setBusy] = useState('')
  const [buscar, setBuscar] = useState('')
  const [nombreAp, setNombreAp] = useState('')
  const [correoAp, setCorreoAp] = useState('')
  const [rucProv, setRucProv] = useState('')
  const [razonProv, setRazonProv] = useState('')
  const [correoProv, setCorreoProv] = useState('')
  const [sociedades, setSociedades] = useState<Sociedad[]>([])
  const [sociedadesAP, setSociedadesAP] = useState<string[]>([])
  const [sociedadesProveedor, setSociedadesProveedor] = useState<string[]>([])
  const [cupos, setCupos] = useState<Cuotas | null>(null)
  const [asignacion, setAsignacion] = useState<{ tipo: 'internos' | 'proveedores'; item: Interno | Proveedor } | null>(null)
  const [sociedadesEditadas, setSociedadesEditadas] = useState<string[]>([])

  const cargar = useCallback(async () => {
    setError('')
    try {
      const response = await fetch(`${api}/administracion/usuarios`, { headers: headers() })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'No se pudieron cargar las cuentas.')
      setData(body)
      const [societyResponse, quotaResponse] = await Promise.all([
        fetch(`${api}/administracion/sociedades`, { headers: headers() }),
        fetch(`${api}/administracion/cupos`, { headers: headers() }),
      ])
      if (societyResponse.ok) setSociedades(await societyResponse.json())
      if (quotaResponse.ok) setCupos(await quotaResponse.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron cargar las cuentas.')
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void cargar(), 0)
    return () => window.clearTimeout(timer)
  }, [cargar])

  async function request(path: string, method: string, body?: unknown) {
    setError('')
    setMensaje('')
    const response = await fetch(`${api}${path}`, { method, headers: headers(), ...(body ? { body: JSON.stringify(body) } : {}) })
    const result = await response.json()
    if (!response.ok) throw new Error(result.detail || 'No se pudo completar la operación.')
    return result
  }

  async function crearInterno(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; setBusy('crear-ap')
    try {
      const result = await request('/administracion/usuarios/cuentas-por-pagar', 'POST', { usuario: correoAp, nombre: nombreAp, sociedades_ids: sociedadesAP })
      setPasswordTemporal(result.password_temporal); setMensaje(`Cuenta ${result.usuario} creada. Entrega la clave temporal por un canal seguro; se pedirá cambiarla al ingresar.`)
      setCorreoAp(''); setNombreAp(''); form.reset(); await cargar()
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo crear la cuenta.') }
    finally { setBusy('') }
  }

  async function crearProveedor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; setBusy('crear-proveedor')
    try {
      const result = await request('/administracion/usuarios/proveedores', 'POST', { ruc: rucProv, razon_social: razonProv, email: correoProv, sociedades_ids: sociedadesProveedor })
      setPasswordTemporal(result.password_temporal); setMensaje(`Cuenta de proveedor ${result.ruc} creada. Entrega la clave temporal por un canal seguro; se pedirá cambiarla al ingresar.`)
      setRucProv(''); setRazonProv(''); setCorreoProv(''); form.reset(); await cargar()
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo crear el proveedor.') }
    finally { setBusy('') }
  }

  async function cambiarEstado(tipo: 'internos' | 'proveedores', item: Interno | Proveedor) {
    setBusy(item.id); setPasswordTemporal('')
    try {
      await request(`/administracion/usuarios/${tipo}/${item.id}`, 'PATCH', { activo: !item.activo })
      setMensaje(`Cuenta ${!item.activo ? 'activada' : 'desactivada'}.`); await cargar()
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo cambiar el estado.') }
    finally { setBusy('') }
  }

  async function guardarSociedades() {
    if (!asignacion || sociedadesEditadas.length === 0) return
    setBusy(asignacion.item.id)
    try {
      await request(`/administracion/usuarios/${asignacion.tipo}/${asignacion.item.id}/sociedades`, 'PUT', { sociedades_ids: sociedadesEditadas })
      setMensaje('Asignación de sociedades actualizada.'); setAsignacion(null); await cargar()
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo actualizar la asignación.') }
    finally { setBusy('') }
  }

  async function restablecer(tipo: 'internos' | 'proveedores', item: Interno | Proveedor) {
    setBusy(item.id); setPasswordTemporal('')
    if (tipo === 'proveedores') { setError('La contraseña del proveedor es global y solo puede restablecerse mediante el proceso seguro de soporte.'); setBusy(''); return }
    const path = `/administracion/usuarios/internos/${item.id}/restablecer-password`
    try {
      const result = await request(path, 'POST')
      setPasswordTemporal(result.password_temporal); setMensaje(`Se generó una clave temporal para ${'usuario' in item ? item.usuario : item.ruc}. Entrégala por un canal seguro; deberá cambiarse al ingresar.`); await cargar()
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo restablecer la contraseña.') }
    finally { setBusy('') }
  }

  async function copiarPassword() {
    try { await navigator.clipboard.writeText(passwordTemporal); setMensaje('Contraseña temporal copiada.') }
    catch { setError('No se pudo copiar. Selecciona y copia la contraseña manualmente.') }
  }

  const filtro = buscar.trim().toLocaleLowerCase('es-PE')
  const internos = data.usuarios_internos.filter(item => item.administrable && `${item.nombre} ${item.usuario}`.toLocaleLowerCase('es-PE').includes(filtro))
  const proveedores = data.proveedores.filter(item => `${item.razon_social} ${item.ruc} ${item.email}`.toLocaleLowerCase('es-PE').includes(filtro))

  const checks = (items: Sociedad[], selected: string[], setSelected: (ids: string[]) => void) => <fieldset className="space-y-2"><legend className="text-sm font-semibold text-brand-navy">Sociedades habilitadas</legend>{items.length === 0 ? <p className="text-sm text-amber-800">IVS todavía no habilitó sociedades para este cliente.</p> : items.map(s => <label key={s.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selected.includes(s.id)} onChange={e => setSelected(e.target.checked ? [...selected, s.id] : selected.filter(id => id !== s.id))} /><span>{s.razon_social} · RUC {s.ruc}</span></label>)}</fieldset>

  return <div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h1 className="text-3xl font-bold text-brand-navy">Usuarios y proveedores</h1><p className="mt-2 text-brand-muted">Administra accesos de esta empresa. Los permisos los asigna el servidor, no el usuario en la pantalla de ingreso.</p></div>
      <button onClick={() => { setCargando(true); void cargar() }} disabled={cargando} className="rounded-xl border border-brand-teal px-4 py-2.5 font-semibold text-brand-teal hover:bg-brand-soft disabled:opacity-50">Actualizar</button>
    </div>

    {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">{error}</div>}
    {mensaje && <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-900">{mensaje}</div>}
    {passwordTemporal && <div className="rounded-xl border border-amber-300 bg-amber-50 p-4"><p className="text-sm font-semibold text-amber-950">Contraseña temporal · se muestra una sola vez</p><div className="mt-2 flex flex-wrap items-center gap-3"><code className="rounded bg-white px-3 py-2 text-base font-bold text-brand-navy">{passwordTemporal}</code><button onClick={() => void copiarPassword()} className="rounded-lg border border-amber-600 px-3 py-2 text-sm font-semibold text-amber-900">Copiar</button></div><p className="mt-2 text-sm text-amber-900">Entrégala directamente al usuario por un canal seguro. Tendrá que cambiarla antes de acceder al portal.</p></div>}

    {cupos && <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{([['Administradores', cupos.administradores], ['Cuentas por pagar', cupos.cuentas_por_pagar], ['Proveedores', cupos.proveedores], ['Sociedades', cupos.sociedades]] as const).map(([label, quota]) => <div key={label} className="rounded-xl border border-slate-200 bg-white p-4"><p className="text-sm text-brand-muted">{label} habilitados</p><p className="mt-1 text-xl font-bold text-brand-navy">{quota.usados} / {quota.maximo}</p></div>)}</section>}

    {asignacion && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4"><section role="dialog" aria-modal="true" aria-labelledby="society-dialog-title" className="w-full max-w-lg space-y-4 rounded-2xl bg-white p-6 shadow-xl"><div><h2 id="society-dialog-title" className="text-xl font-bold text-brand-navy">Sociedades asignadas</h2><p className="text-sm text-brand-muted">{'nombre' in asignacion.item ? asignacion.item.nombre : asignacion.item.razon_social}</p></div>{checks(sociedades, sociedadesEditadas, setSociedadesEditadas)}<div className="flex justify-end gap-3"><button onClick={()=>setAsignacion(null)} className="rounded-lg border px-4 py-2">Cancelar</button><button disabled={busy===asignacion.item.id||sociedadesEditadas.length===0} onClick={()=>void guardarSociedades()} className="rounded-lg bg-brand-teal px-4 py-2 font-semibold text-white disabled:opacity-50">Guardar asignación</button></div></section></div>}

    <div className="grid gap-5 xl:grid-cols-2">
      <form onSubmit={crearInterno} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
        <div><h2 className="text-lg font-bold text-brand-navy">Crear cuenta de cuentas por pagar</h2><p className="mt-1 text-sm text-brand-muted">El rol se fija aquí como analista; solo el bootstrap controlado puede crear administradores.</p></div>
        <label className="block text-sm font-semibold text-brand-navy">Nombre completo<input required minLength={2} maxLength={200} value={nombreAp} onChange={event => setNombreAp(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal" /></label>
        <label className="block text-sm font-semibold text-brand-navy">Correo corporativo<input required type="email" value={correoAp} onChange={event => setCorreoAp(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal" /></label>
        {checks(sociedades, sociedadesAP, setSociedadesAP)}
        <button disabled={busy === 'crear-ap' || sociedadesAP.length === 0} className="rounded-lg bg-brand-teal px-4 py-2.5 font-semibold text-white disabled:opacity-50">{busy === 'crear-ap' ? 'Creando…' : 'Crear cuenta'}</button>
      </form>
      <form onSubmit={crearProveedor} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
        <div><h2 className="text-lg font-bold text-brand-navy">Crear cuenta de proveedor</h2><p className="mt-1 text-sm text-brand-muted">El acceso se vincula al RUC y empieza con cambio obligatorio de contraseña.</p></div>
        <label className="block text-sm font-semibold text-brand-navy">RUC<input required inputMode="numeric" pattern="\d{11}" maxLength={11} value={rucProv} onChange={event => setRucProv(event.target.value.replace(/\D/g, ''))} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal" /></label>
        <label className="block text-sm font-semibold text-brand-navy">Razón social<input required minLength={2} maxLength={200} value={razonProv} onChange={event => setRazonProv(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal" /></label>
        <label className="block text-sm font-semibold text-brand-navy">Correo de contacto<input required type="email" value={correoProv} onChange={event => setCorreoProv(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal" /></label>
        {checks(sociedades, sociedadesProveedor, setSociedadesProveedor)}
        <button disabled={busy === 'crear-proveedor' || sociedadesProveedor.length === 0} className="rounded-lg bg-brand-teal px-4 py-2.5 font-semibold text-white disabled:opacity-50">{busy === 'crear-proveedor' ? 'Creando…' : 'Crear proveedor'}</button>
      </form>
    </div>

    <label className="block max-w-xl text-sm font-semibold text-brand-navy">Buscar cuenta<input value={buscar} onChange={event => setBuscar(event.target.value)} placeholder="Nombre, correo o RUC" className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 font-normal" /></label>

    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 p-5"><h2 className="text-lg font-bold text-brand-navy">Cuentas internas · Cuentas por pagar</h2></div>
      {cargando ? <p className="p-5 text-brand-muted">Cargando cuentas…</p> : internos.length === 0 ? <p className="p-5 text-brand-muted">No hay cuentas internas para mostrar.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[700px] text-left text-sm"><thead className="bg-brand-soft text-brand-navy"><tr><th className="p-3">Usuario</th><th className="p-3">Rol</th><th className="p-3">Sociedades</th><th className="p-3">Estado</th><th className="p-3">Acciones</th></tr></thead><tbody>{internos.map(item => <tr key={item.id} className="border-t border-slate-100"><td className="p-3"><strong>{item.nombre}</strong><div className="text-brand-muted">{item.usuario}</div></td><td className="p-3">Analista de cuentas por pagar</td><td className="p-3">{item.sociedades_ids.map(id=>sociedades.find(s=>s.id===id)?.ruc).filter(Boolean).join(', ') || '—'}</td><td className="p-3">{item.activo ? 'Activa' : 'Desactivada'}{item.debe_cambiar_password ? ' · cambio de contraseña pendiente' : ''}</td><td className="space-x-2 p-3"><button disabled={busy === item.id} onClick={() => {setAsignacion({tipo:'internos',item});setSociedadesEditadas(item.sociedades_ids)}} className="font-semibold text-brand-teal">Sociedades</button><button disabled={busy === item.id} onClick={() => void cambiarEstado('internos', item)} className="font-semibold text-brand-teal">{item.activo ? 'Desactivar' : 'Activar'}</button><button disabled={busy === item.id || !item.activo} onClick={() => void restablecer('internos', item)} className="font-semibold text-brand-teal disabled:opacity-50">Restablecer clave</button></td></tr>)}</tbody></table></div>}
    </section>

    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 p-5"><h2 className="text-lg font-bold text-brand-navy">Cuentas de proveedores</h2></div>
      {cargando ? <p className="p-5 text-brand-muted">Cargando cuentas…</p> : proveedores.length === 0 ? <p className="p-5 text-brand-muted">No hay proveedores para mostrar.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[850px] text-left text-sm"><thead className="bg-brand-soft text-brand-navy"><tr><th className="p-3">Proveedor</th><th className="p-3">RUC</th><th className="p-3">Correo</th><th className="p-3">Estado</th><th className="p-3">Sociedades habilitadas</th><th className="p-3">Acciones</th></tr></thead><tbody>{proveedores.map(item => <tr key={item.id} className="border-t border-slate-100"><td className="p-3 font-semibold">{item.razon_social}</td><td className="p-3">{item.ruc}</td><td className="p-3">{item.email}</td><td className="p-3">{item.activo ? 'Activa' : 'Desactivada'}{item.debe_cambiar_password ? ' · cambio de contraseña pendiente' : ''}</td><td className="p-3">{item.sociedades_ids.map(id=>sociedades.find(s=>s.id===id)?.ruc).filter(Boolean).join(', ') || '—'}</td><td className="space-x-2 p-3"><button disabled={busy === item.id} onClick={() => {setAsignacion({tipo:'proveedores',item});setSociedadesEditadas(item.sociedades_ids)}} className="font-semibold text-brand-teal">Sociedades</button><button disabled={busy === item.id} onClick={() => void cambiarEstado('proveedores', item)} className="font-semibold text-brand-teal">{item.activo ? 'Desactivar' : 'Activar'}</button></td></tr>)}</tbody></table></div>}
    </section>
    <p className="text-xs text-brand-muted">El administrador puede gestionar cuentas de esta instalación. La cuenta administradora y su rol se crean por el proceso de bootstrap del servidor y no se pueden crear desde esta pantalla.</p>
  </div>
}
