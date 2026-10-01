'use client'

import { Fragment, useEffect, useState } from 'react'
import Link from 'next/link'
import styles from './ordenes.module.css'

type Posicion = { id:string; numero:string; material:string; tipo?:'material'|'servicio'; codigo_servicio?:string|null; paquete_servicio?:string|null; numero_servicio?:string|null; cantidad_servicio_aceptada?:number; cantidad_facturable?:number; saldo_facturable?:number; descripcion:string; unidad:string; cantidad:number; precio_unitario:number; tasa_igv:number; total:number; cantidad_facturada:number; cantidad_pendiente:number; saldo:number }
type Orden = {
  id: string; numero: string; monto_total: number; estado: string
  descripcion: string | null; creado_en: string | null
  monto_facturado: number; saldo_por_facturar: number
  estado_facturacion: 'pendiente' | 'parcial' | 'facturada' | 'cancelada'
}
const etiquetas = { pendiente: 'Sin facturar', parcial: 'Parcialmente facturada', facturada: 'Facturada', cancelada: 'Cancelada' }
const dinero = (valor: number) => new Intl.NumberFormat('es-PE', { style: 'currency', currency: 'PEN' }).format(valor)

export default function Ordenes() {
  const [ordenes, setOrdenes] = useState<Orden[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [busqueda, setBusqueda] = useState('')
  const [estado, setEstado] = useState('por_facturar')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [abierta, setAbierta] = useState('')
  const [detalle, setDetalle] = useState<Record<string,{posiciones:Posicion[];bloqueo:string}>>({})
  const [cargandoDetalle, setCargandoDetalle] = useState('')
  const [errorDetalle, setErrorDetalle] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const estadoInicial=new URLSearchParams(window.location.search).get('estado')
    const filtroTimer=window.setTimeout(()=>{if(estadoInicial==='por_facturar')setEstado('por_facturar')},0)
    async function cargar() {
      setCargando(true)
      setError('')
      try {
        const token = localStorage.getItem('access_token')
        if (!token) throw new Error('Tu sesión terminó. Vuelve a iniciar sesión para consultar tus órdenes.')
        const res = await fetch('http://localhost:8000/ordenes', {
          headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
        })
        if (res.status === 401) throw new Error('Tu sesión terminó. Vuelve a iniciar sesión para consultar tus órdenes.')
        if (!res.ok) throw new Error('No pudimos consultar las órdenes. Inténtalo nuevamente.')
        const data: Orden[] = await res.json()
        if (!Array.isArray(data) || data.some(o => !Number.isFinite(o.saldo_por_facturar) || !Number.isFinite(o.monto_facturado) || !(o.estado_facturacion in etiquetas))) {
          throw new Error('El servicio de órdenes necesita actualizarse. Reinicia el backend y vuelve a intentar.')
        }
        setOrdenes(data)
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof TypeError ? 'No hay conexión con el servicio de órdenes. Vuelve a intentar en unos momentos.' : err instanceof Error ? err.message : 'No se pudieron cargar las órdenes.')
      } finally {
        if (!controller.signal.aborted) setCargando(false)
      }
    }
    cargar()
    return () => { controller.abort(); window.clearTimeout(filtroTimer) }
  }, [revision])

  const pendientes = ordenes.filter(o => ['pendiente', 'parcial'].includes(o.estado_facturacion))
  const fechasInvalidas = Boolean(desde && hasta && desde > hasta)
  const visibles = ordenes.filter(o => {
    const texto = `${o.numero} ${o.descripcion || ''}`.toLocaleLowerCase('es')
    const fecha = o.creado_en?.slice(0, 10) || ''
    return texto.includes(busqueda.trim().toLocaleLowerCase('es')) &&
      (estado === 'todas' || (estado === 'por_facturar' ? ['pendiente', 'parcial'].includes(o.estado_facturacion) : estado === o.estado_facturacion)) &&
      (!desde || fecha >= desde) && (!hasta || Boolean(fecha && fecha <= hasta))
  })
  const limpiar = () => { setBusqueda(''); setEstado('todas'); setDesde(''); setHasta('') }
  const disponible = !cargando && !error
  async function toggleDetalle(o:Orden) {
    if (abierta===o.id) { setAbierta(''); return }
    setAbierta(o.id); setErrorDetalle('')
    if (detalle[o.id]) return
    setCargandoDetalle(o.id)
    try {
      const token=localStorage.getItem('access_token')
      const res=await fetch(`http://localhost:8000/ordenes/${o.id}/posiciones`,{headers:{Authorization:`Bearer ${token||''}`}})
      const data=await res.json()
      if(!res.ok) throw new Error(typeof data.detail==='string'?data.detail:'No se pudo cargar el detalle del pedido.')
      setDetalle(prev=>({...prev,[o.id]:data}))
    } catch(e) { setErrorDetalle(e instanceof Error?e.message:'No se pudo cargar el detalle del pedido.') }
    finally { setCargandoDetalle('') }
  }

  return <div className={styles.page}>
    <header className={styles.header}>
      <div><h1>Órdenes de compra</h1><p>Consulta tus órdenes y el saldo pendiente de facturar.</p></div>
      <button onClick={() => setRevision(v => v + 1)} disabled={cargando}>Actualizar</button>
    </header>
    <section className={styles.summary} aria-label="Resumen de órdenes">
      <article><span>Total de órdenes</span><strong>{disponible ? ordenes.length : '—'}</strong></article>
      <article><span>Pendientes de facturar</span><strong>{disponible ? pendientes.length : '—'}</strong></article>
      <article><span>Saldo pendiente</span><strong>{disponible ? dinero(pendientes.reduce((s, o) => s + o.saldo_por_facturar, 0)) : '—'}</strong></article>
    </section>
    <section className={styles.filters} aria-label="Filtros de órdenes">
      <label>Buscar orden<input type="search" placeholder="Número o descripción" value={busqueda} onChange={e => setBusqueda(e.target.value)} /></label>
      <label>Facturación<select value={estado} onChange={e => setEstado(e.target.value)}>
        <option value="por_facturar">Pendientes de facturar</option><option value="todas">Todas las órdenes</option>
        {Object.entries(etiquetas).map(([valor, texto]) => <option key={valor} value={valor}>{texto}</option>)}
      </select></label>
      <label>Desde<input type="date" value={desde} onChange={e => setDesde(e.target.value)} /></label>
      <label>Hasta<input type="date" value={hasta} onChange={e => setHasta(e.target.value)} /></label>
      <button onClick={limpiar}>Limpiar filtros</button>
    </section>
    {fechasInvalidas && <p role="alert" className={styles.error}>La fecha «Desde» no puede ser posterior a «Hasta».</p>}
    <section className={styles.results} aria-busy={cargando}>
      {cargando ? <p role="status">Cargando órdenes de compra…</p> : error ? <div role="alert"><p className={styles.error}>{error}</p><button onClick={() => setRevision(v => v + 1)}>Reintentar</button></div> : fechasInvalidas ? <p>Corrige el rango de fechas para consultar los resultados.</p> : <>
        <p className={styles.count} aria-live="polite">{visibles.length} de {ordenes.length} órdenes · Fechas de creación de la orden</p>
        {visibles.length === 0 ? <div className={styles.empty}><h2>{ordenes.length ? 'No hay órdenes con estos filtros' : 'Aún no tienes órdenes de compra'}</h2><p>{ordenes.length ? 'Prueba otro estado, número o rango de fechas.' : 'Las órdenes asignadas a tu empresa aparecerán aquí.'}</p>{ordenes.length > 0 && <button onClick={limpiar}>Ver todas las órdenes</button>}</div> : <div className={styles.scroll}><table>
          <thead><tr><th>Detalle</th><th>Orden / descripción</th><th>Fecha</th><th>Total</th><th>Facturado</th><th>Saldo por facturar</th><th>Facturación</th><th>Estado de la orden</th><th>Acciones</th></tr></thead>
          <tbody>{visibles.map(o => <Fragment key={o.id}><tr>
            <td><button type="button" className={styles.detailToggle} aria-expanded={abierta===o.id} aria-label={`${abierta===o.id?'Ocultar':'Ver'} posiciones de ${o.numero}`} onClick={()=>toggleDetalle(o)}>{abierta===o.id?'−':'+'}</button></td>
            <td><strong>{o.numero}</strong><small>{o.descripcion || 'Sin descripción'}</small></td>
            <td>{o.creado_en ? new Date(o.creado_en).toLocaleDateString('es-PE') : '—'}</td>
            <td className={styles.money}>{dinero(o.monto_total)}</td><td className={styles.money}>{dinero(o.monto_facturado)}</td>
            <td className={styles.money}><strong>{o.estado_facturacion === 'cancelada' ? 'No aplica' : dinero(o.saldo_por_facturar)}</strong></td>
            <td><span className={styles.badge} data-status={o.estado_facturacion}>{etiquetas[o.estado_facturacion]}</span></td>
            <td>{o.estado.replaceAll('_', ' ')}</td><td>{['pendiente','parcial'].includes(o.estado_facturacion) && <Link href={`/dashboard/facturas/nueva?orden=${o.id}`}>Registrar factura</Link>}</td>
          </tr>{abierta===o.id&&<tr className={styles.detailRow}><td colSpan={9}><h3>Detalle de {o.numero}</h3>{cargandoDetalle===o.id?<p role="status">Cargando posiciones…</p>:errorDetalle?<p role="alert" className={styles.error}>{errorDetalle}</p>:detalle[o.id]&&<>{detalle[o.id].bloqueo&&<p className={styles.error}>{detalle[o.id].bloqueo}</p>}{detalle[o.id].posiciones.length?<div className={styles.scroll}><table><thead><tr><th>Tipo</th><th>Posición SAP</th><th>Material / servicio</th><th>Descripción</th><th>Unidad</th><th>Cantidad pedida</th><th>Cantidad aceptada</th><th>Cantidad pendiente pedido</th><th>Cantidad pendiente facturable</th><th>Cantidad facturada</th><th>Total posición</th><th>Saldo por facturar</th></tr></thead><tbody>{detalle[o.id].posiciones.map(p=><tr key={p.id}><td>{p.tipo==='servicio'?'Servicio':'Material'}</td><td>{p.numero}{p.tipo==='servicio'&&p.numero_servicio?` / servicio ${p.numero_servicio}`:''}</td><td>{p.tipo==='servicio'?p.codigo_servicio||'Servicio':p.material}</td><td>{p.descripcion}{p.tipo==='servicio'&&p.paquete_servicio?` · paquete ${p.paquete_servicio}`:''}</td><td>{p.unidad}</td><td>{p.cantidad}</td><td>{p.tipo==='servicio'?p.cantidad_servicio_aceptada||0:'—'}</td><td>{p.cantidad_pendiente}</td><td>{p.cantidad_facturable??p.cantidad_pendiente}</td><td>{p.cantidad_facturada}</td><td className={styles.money}>{dinero(p.total)}</td><td className={styles.money}><strong>{dinero(p.tipo==='servicio'?p.saldo_facturable??0:p.saldo)}</strong></td></tr>)}</tbody><tfoot><tr><th colSpan={11}>Saldo total pendiente del pedido</th><td className={styles.money}><strong>{dinero(detalle[o.id].posiciones.reduce((s,p)=>s+(p.tipo==='servicio'?p.saldo_facturable??0:p.saldo),0))}</strong></td></tr></tfoot></table></div>:<p>Este pedido no tiene posiciones detalladas cargadas. El saldo total del pedido es {dinero(o.saldo_por_facturar)}.</p>}{detalle[o.id].posiciones.some(p=>p.tipo==='servicio')&&<p>Las posiciones de servicio solo se pueden facturar con sus cantidades aceptadas en una hoja de entrada de servicios.</p>}</>}</td></tr>}</Fragment>)}</tbody>
        </table></div>}
      </>}
    </section>
    <p className={styles.note}>El saldo considera las facturas asociadas a cada orden, excluyendo anuladas, canceladas y rechazadas. Las órdenes canceladas no se incluyen en el pendiente.</p>
  </div>
}
