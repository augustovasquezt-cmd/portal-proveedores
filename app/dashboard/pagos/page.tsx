'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import styles from './pagos.module.css'

type Factura={id:string;serie:string;correlativo:string;monto_total:number;estado:string;creado_en:string}
type Grupo='revision'|'correccion'|'aprobada'|'pagada'|'otra'
const dinero=(n:number)=>new Intl.NumberFormat('es-PE',{style:'currency',currency:'PEN'}).format(n)
const normalizar=(s:string)=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim()
function grupo(estado:string):Grupo{
 const e=normalizar(estado)
 if(e.includes('pagad'))return 'pagada'
 if(e.includes('rechaz')||e.includes('observad')||e.includes('correccion'))return 'correccion'
 if(e.includes('aprob')||e.includes('aceptad'))return 'aprobada'
 if(e.includes('revision'))return 'revision'
 return 'otra'
}
const etiquetas:Record<Grupo,string>={revision:'En revisión',correccion:'Requiere corrección',aprobada:'Aprobada · pendiente de pago',pagada:'Pagada',otra:'Registrada'}
const fecha=(v:string)=>v?new Intl.DateTimeFormat('es-PE',{dateStyle:'medium'}).format(new Date(v)):'—'

export default function Pagos(){
 const [facturas,setFacturas]=useState<Factura[]>([])
 const [filtro,setFiltro]=useState<'todas'|Grupo>('todas')
 const [busqueda,setBusqueda]=useState('')
 const [cargando,setCargando]=useState(true)
 const [error,setError]=useState('')
 const [actualizar,setActualizar]=useState(0)
 const cargar=useCallback(async(signal:AbortSignal)=>{
  setCargando(true);setError('')
  try{
   const token=localStorage.getItem('access_token')
   if(!token)throw new Error('Tu sesión terminó. Vuelve a iniciar sesión para consultar tus facturas.')
   const r=await fetch('http://localhost:8000/facturas',{headers:{Authorization:`Bearer ${token}`},signal})
   if(r.status===401)throw new Error('Tu sesión terminó. Vuelve a iniciar sesión para consultar tus facturas.')
   if(!r.ok)throw new Error('No se pudieron cargar tus facturas. Inténtalo nuevamente.')
   const data=await r.json()
   if(!signal.aborted)setFacturas(Array.isArray(data)?data:[])
  }catch(e){if(!signal.aborted)setError(e instanceof Error?e.message:'No se pudieron cargar tus facturas.')}
  finally{if(!signal.aborted)setCargando(false)}
 },[])
 useEffect(()=>{const c=new AbortController();const timer=window.setTimeout(()=>cargar(c.signal),0);return()=>{window.clearTimeout(timer);c.abort()}},[cargar,actualizar])
 const grupos=useMemo(()=>({revision:facturas.filter(f=>grupo(f.estado)==='revision'),correccion:facturas.filter(f=>grupo(f.estado)==='correccion'),aprobada:facturas.filter(f=>grupo(f.estado)==='aprobada'),pagada:facturas.filter(f=>grupo(f.estado)==='pagada')}),[facturas])
 const visibles=facturas.filter(f=>{
  const texto=normalizar(`${f.serie}-${f.correlativo} ${f.estado}`)
  return (filtro==='todas'||grupo(f.estado)===filtro)&&texto.includes(normalizar(busqueda.trim()))
 }).sort((a,b)=>new Date(b.creado_en).getTime()-new Date(a.creado_en).getTime())
 const tarjetas:[string,'todas'|Grupo,number,string][]=[
  ['Facturas registradas','todas',facturas.length,dinero(facturas.reduce((s,f)=>s+f.monto_total,0))],
  ['En revisión','revision',grupos.revision.length,dinero(grupos.revision.reduce((s,f)=>s+f.monto_total,0))],
  ['Requieren corrección','correccion',grupos.correccion.length,dinero(grupos.correccion.reduce((s,f)=>s+f.monto_total,0))],
  ['Aprobadas · pendientes de pago','aprobada',grupos.aprobada.length,dinero(grupos.aprobada.reduce((s,f)=>s+f.monto_total,0))],
  ['Pagadas','pagada',grupos.pagada.length,dinero(grupos.pagada.reduce((s,f)=>s+f.monto_total,0))],
 ]
 return <main className={styles.page}>
  <header className={styles.header}><div><p className={styles.eyebrow}>CUENTAS POR COBRAR</p><h1>Seguimiento de facturas y pagos</h1><p>Consulta el estado de revisión de tus facturas y el avance de pago informado por tu cliente.</p></div><button onClick={()=>setActualizar(v=>v+1)} disabled={cargando}>Actualizar</button></header>
  {error&&<div role="alert" className={styles.error}>{error}<button onClick={()=>setActualizar(v=>v+1)}>Reintentar</button></div>}
  <section className={styles.cards} aria-label="Resumen de facturas">{tarjetas.map(([titulo,key,cantidad,monto])=><button type="button" key={key} className={styles.card} data-selected={filtro===key} onClick={()=>setFiltro(filtro===key&&key!=='todas'?'todas':key)}><span>{titulo}</span><strong>{cargando?'—':cantidad}</strong><small>{cargando?'Consultando…':monto}</small></button>)}</section>
  <section className={styles.tablePanel}><div className={styles.filters}><label>Buscar factura<input type="search" placeholder="Serie, número o estado" value={busqueda} onChange={e=>setBusqueda(e.target.value)}/></label><label>Estado<select value={filtro} onChange={e=>setFiltro(e.target.value as 'todas'|Grupo)}><option value="todas">Todos los estados</option><option value="revision">En revisión</option><option value="correccion">Requieren corrección</option><option value="aprobada">Aprobadas · pendientes de pago</option><option value="pagada">Pagadas</option><option value="otra">Otras facturas registradas</option></select></label><Link href="/dashboard/facturas">Ir a mis facturas →</Link></div>
   {cargando?<p className={styles.empty} role="status">Cargando estados de factura…</p>:error?null:visibles.length===0?<div className={styles.empty}><h2>{facturas.length?'No hay facturas con estos filtros':'Aún no hay facturas registradas'}</h2><p>{facturas.length?'Prueba con otro estado o número.':'Cuando registres una factura, podrás seguir aquí su estado.'}</p>{facturas.length===0&&<Link href="/dashboard/facturas/nueva">Registrar factura</Link>}</div>:<div className={styles.scroll}><table><thead><tr><th>Factura</th><th>Fecha de registro</th><th>Estado actual</th><th className={styles.money}>Importe</th><th>Seguimiento</th></tr></thead><tbody>{visibles.map(f=>{const g=grupo(f.estado);return <tr key={f.id}><td><strong>{f.serie}-{f.correlativo}</strong></td><td>{fecha(f.creado_en)}</td><td><span className={styles.badge} data-status={g}>{etiquetas[g]}</span></td><td className={styles.money}>{dinero(f.monto_total)}</td><td><Link href={`/dashboard/facturas/${f.id}`}>Ver factura →</Link></td></tr>})}</tbody></table></div>}
  </section>
  <p className={styles.note}>Los estados y montos reflejan la información registrada en el portal. La fecha y el comprobante de pago aparecerán cuando tu cliente los informe al sistema.</p>
 </main>
}
