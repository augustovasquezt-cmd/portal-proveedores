'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import styles from './inicio.module.css'

type Orden={id:string;numero:string;monto_total:number;estado_facturacion:string;saldo_por_facturar:number;creado_en:string|null}
type Factura={id:string;serie:string;correlativo:string;monto_total:number;estado:string;creado_en:string}
type Tile={label:string;value:string;detail:string;href:string;icon:string;tone:string}
const api='http://localhost:8000'
const money=(n:number)=>new Intl.NumberFormat('es-PE',{style:'currency',currency:'PEN'}).format(n)
const normalized=(s:string)=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim()
const date=(s:string)=>s?new Intl.DateTimeFormat('es-PE',{dateStyle:'medium'}).format(new Date(s)): '—'

export default function Dashboard(){
 const [razonSocial,setRazonSocial]=useState('')
 const [ruc,setRuc]=useState('')
 const [ordenes,setOrdenes]=useState<Orden[]>([])
 const [facturas,setFacturas]=useState<Factura[]>([])
 const [cargando,setCargando]=useState(true)
 const [error,setError]=useState('')
 const [revision,setRevision]=useState(0)
 useEffect(()=>{
  const controller=new AbortController()
  const identityTimer=window.setTimeout(()=>{setRazonSocial(localStorage.getItem('razon_social')||'Proveedor');setRuc(localStorage.getItem('ruc')||'')},0)
  async function cargar(){
   setCargando(true);setError('')
   try{
    const token=localStorage.getItem('access_token')||''
    const headers={Authorization:`Bearer ${token}`}
    const [rO,rF]=await Promise.all([fetch(`${api}/ordenes`,{headers,signal:controller.signal}),fetch(`${api}/facturas`,{headers,signal:controller.signal})])
    if(!rO.ok||!rF.ok)throw new Error('No pudimos cargar el resumen. Actualiza e inténtalo de nuevo.')
    const [o,f]=await Promise.all([rO.json(),rF.json()])
    if(!controller.signal.aborted){setOrdenes(Array.isArray(o)?o:[]);setFacturas(Array.isArray(f)?f:[])}
   }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'No se pudo cargar el resumen.')}
   finally{if(!controller.signal.aborted)setCargando(false)}
  }
  cargar();return()=>{controller.abort();window.clearTimeout(identityTimer)}
 },[revision])
 const metricas=useMemo(()=>{
  const pendientes=ordenes.filter(o=>['pendiente','parcial'].includes(o.estado_facturacion))
  const estados=facturas.map(f=>({factura:f,estado:normalized(f.estado)}))
  const revision=estados.filter(x=>x.estado.includes('revision')||x.estado.includes('revisi'))
  const correccion=estados.filter(x=>x.estado.includes('rechaz')||x.estado.includes('observad')||x.estado.includes('correccion'))
  const aprobadas=estados.filter(x=>(x.estado.includes('aprob')||x.estado.includes('aceptad'))&&!x.estado.includes('pagad'))
  const pagadas=estados.filter(x=>x.estado.includes('pagad'))
  return {pendientes,revision,correccion,aprobadas,pagadas}
 },[ordenes,facturas])
 const tiles:Tile[]=[
  {label:'Órdenes por facturar',value:cargando?'—':String(metricas.pendientes.length),detail:cargando?'Consultando…':`${money(metricas.pendientes.reduce((s,o)=>s+o.saldo_por_facturar,0))} de saldo pendiente`,href:'/dashboard/ordenes?estado=por_facturar',icon:'OC',tone:'teal'},
  {label:'Facturas en revisión',value:cargando?'—':String(metricas.revision.length),detail:cargando?'Consultando…':`${money(metricas.revision.reduce((s,x)=>s+x.factura.monto_total,0))} en revisión`,href:'/dashboard/facturas?estado=revision',icon:'FR',tone:'blue'},
  {label:'Requieren corrección',value:cargando?'—':String(metricas.correccion.length),detail:cargando?'Consultando…':`${money(metricas.correccion.reduce((s,x)=>s+x.factura.monto_total,0))} por corregir`,href:'/dashboard/facturas?estado=correccion',icon:'!',tone:'amber'},
  {label:'Aprobadas pendientes de pago',value:cargando?'—':String(metricas.aprobadas.length),detail:cargando?'Consultando…':`${money(metricas.aprobadas.reduce((s,x)=>s+x.factura.monto_total,0))} por cobrar`,href:'/dashboard/facturas?estado=aprobadas',icon:'AP',tone:'blue'},
  {label:'Facturas pagadas',value:cargando?'—':String(metricas.pagadas.length),detail:cargando?'Consultando…':`${money(metricas.pagadas.reduce((s,x)=>s+x.factura.monto_total,0))} pagadas`,href:'/dashboard/facturas?estado=pagadas',icon:'OK',tone:'green'},
 ]
 const recientes=[...facturas].sort((a,b)=>new Date(b.creado_en).getTime()-new Date(a.creado_en).getTime()).slice(0,5)
 return <div className={styles.home}>
  <header className={styles.header}><div><p className={styles.eyebrow}>PORTAL DE PROVEEDORES</p><h1>Bienvenido, {razonSocial}</h1><p className={styles.subhead}>RUC: {ruc||'—'} · Aquí tienes el estado de tus pedidos y facturas.</p></div><div className={styles.actions}><Link className={styles.primary} href="/dashboard/facturas/nueva">+ Registrar factura</Link><Link className={styles.secondary} href="/dashboard/ordenes">Ver pedidos</Link></div></header>
  {error&&<div role="alert" className={styles.error}>{error}<button onClick={()=>setRevision(v=>v+1)}>Reintentar</button></div>}
  <section aria-label="Resumen de facturación" className={styles.tiles}>{tiles.map(t=><Link key={t.label} href={t.href} className={styles.tile} data-tone={t.tone}><span className={styles.tileIcon} aria-hidden="true">{t.icon}</span><span className={styles.tileLabel}>{t.label}</span><strong>{t.value}</strong><span className={styles.tileDetail}>{t.detail}</span><span className={styles.tileLink}>Ver detalle →</span></Link>)}</section>
  <div className={styles.lower}>
   <section className={styles.panel}><div className={styles.panelHeader}><div><h2>Facturas recientes</h2><p>Consulta el estado y abre el detalle de cada factura.</p></div><Link href="/dashboard/facturas">Ver todas</Link></div>
    {cargando?<p role="status" className={styles.empty}>Cargando facturas…</p>:recientes.length===0?<div className={styles.empty}><h3>Aún no registras facturas</h3><p>Cuando envíes una factura, podrás seguir aquí su revisión y pago.</p><Link href="/dashboard/facturas/nueva">Registrar mi primera factura</Link></div>:<div className={styles.recentList}>{recientes.map(f=><Link href={`/dashboard/facturas/${f.id}`} className={styles.recentItem} key={f.id}><span className={styles.invoiceIcon}>F</span><span className={styles.recentInfo}><strong>{f.serie}-{f.correlativo}</strong><small>{date(f.creado_en)}</small></span><span className={styles.status}>{f.estado}</span><strong className={styles.amount}>{money(f.monto_total)}</strong><span aria-hidden="true">›</span></Link>)}</div>}
   </section>
   <aside className={styles.sidePanel}><h2>Accesos rápidos</h2><Link href="/dashboard/ordenes">📋 <span><strong>Órdenes de compra</strong><small>Consulta saldos y posiciones pendientes</small></span> →</Link><Link href="/dashboard/facturas/nueva">＋ <span><strong>Registrar factura</strong><small>Sube el XML y PDF o registra con PDF</small></span> →</Link><Link href="/dashboard/facturas">🧾 <span><strong>Mis facturas</strong><small>Revisa estados y documentos</small></span> →</Link><p className={styles.sapNote}>El envío a SAP aparecerá cuando la conexión de tu empresa esté configurada.</p></aside>
  </div>
 </div>
}
