'use client'

import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import styles from './tickets.module.css'

type Referencia={tipo:'pedido'|'factura'|'documento';id:string;numero:string;descripcion:string;pedido:string}
type Adjunto={id:string;nombre:string}
type Mensaje={id:string;autor_tipo:string;mensaje:string;creado_en:string|null;adjuntos:Adjunto[]}
type Ticket={id:string;numero:string;asunto:string;descripcion:string;categoria:string;prioridad:string;estado:string;creado_en:string|null;referencia:{tipo:string;numero:string|null;orden_id:string|null}|null;mensajes:Mensaje[];adjuntos:Adjunto[]}
const api='http://localhost:8000'
const tipoTitulo:Record<string,string>={pedido:'Orden de compra',factura:'Factura',documento:'Documento asociado',general:'Consulta general'}
const categorias:[string,string][]=[['pedido','Problema con una orden de compra'],['factura','Observación de una factura'],['documento','Problema con un documento (ingreso, servicio o guía)'],['pago','Consulta de pago'],['acceso','Acceso o soporte técnico'],['otro','Otra consulta']]
const estadoLabel:Record<string,string>={abierto:'Abierto',esperando_comprador:'Esperando al comprador',esperando_proveedor:'Requiere información del proveedor',resuelto:'Resuelto',cerrado:'Cerrado'}
const fecha=(v:string|null)=>v?new Intl.DateTimeFormat('es-PE',{dateStyle:'medium',timeStyle:'short'}).format(new Date(v)):'—'
const auth=()=>({Authorization:`Bearer ${localStorage.getItem('access_token')||''}`})

export default function Tickets(){
 const [tickets,setTickets]=useState<Ticket[]>([]);const [referencias,setReferencias]=useState<Referencia[]>([])
 const [cargando,setCargando]=useState(true);const [error,setError]=useState('');const [recarga,setRecarga]=useState(0)
 const [categoria,setCategoria]=useState('factura');const [referenciaId,setReferenciaId]=useState('');const [asunto,setAsunto]=useState('');const [descripcion,setDescripcion]=useState('');const [prioridad,setPrioridad]=useState('normal');const [archivos,setArchivos]=useState<File[]>([])
 const [guardando,setGuardando]=useState(false);const [abierto,setAbierto]=useState('');const [mensaje,setMensaje]=useState('');const [archivosMensaje,setArchivosMensaje]=useState<File[]>([]);const [enviandoMensaje,setEnviandoMensaje]=useState(false);const [filtro,setFiltro]=useState('todos');const [busqueda,setBusqueda]=useState('')
 const cargar=useCallback(async(signal:AbortSignal)=>{
  setCargando(true);setError('')
  try{
   const [rt,rr]=await Promise.all([fetch(`${api}/tickets`,{headers:auth(),signal}),fetch(`${api}/tickets/referencias`,{headers:auth(),signal})])
   const [td,rd]=await Promise.all([rt.json(),rr.json()])
   if(!rt.ok||!rr.ok)throw new Error(td.detail||rd.detail||'No se pudieron cargar los tickets.')
   if(!signal.aborted){setTickets(td);setReferencias(rd)}
  }catch(e){if(!signal.aborted)setError(e instanceof Error?e.message:'No se pudieron cargar los tickets.')}
  finally{if(!signal.aborted)setCargando(false)}
 },[])
 useEffect(()=>{const c=new AbortController();const timer=window.setTimeout(()=>cargar(c.signal),0);return()=>{window.clearTimeout(timer);c.abort()}},[cargar,recarga])
 const tipoRef=useMemo(()=>categoria==='pedido'?'pedido':categoria==='factura'||categoria==='pago'?'factura':categoria==='documento'?'documento':'general',[categoria])
 const opciones=referencias.filter(r=>r.tipo===tipoRef)
 const seleccion=opciones.find(r=>r.id===referenciaId)
 function cambiarCategoria(v:string){setCategoria(v);setReferenciaId('');setError('')}
 function validarArchivos(files:File[]){if(files.length>5)return 'Adjunta hasta 5 archivos por envío.';if(files.some(f=>f.size>5*1024*1024))return 'Cada archivo puede pesar hasta 5 MB.';if(files.reduce((n,f)=>n+f.size,0)>20*1024*1024)return 'El tamaño total de los adjuntos supera 20 MB.';if(files.some(f=>!['application/pdf','image/png','image/jpeg','text/xml','application/xml'].includes(f.type)&&! /\.(pdf|png|jpe?g|xml)$/i.test(f.name)))return 'Adjunta archivos PDF, PNG, JPG o XML.';return ''}
 function tomarArchivos(e:ChangeEvent<HTMLInputElement>,modo:'nuevo'|'mensaje'){const files=Array.from(e.target.files||[]);const issue=validarArchivos(files);if(issue){setError(issue);return}setError('');if(modo==='nuevo')setArchivos(files);else setArchivosMensaje(files)}
 async function crear(e:FormEvent){e.preventDefault();const form=e.currentTarget as HTMLFormElement;if(categoria!=='acceso'&&categoria!=='otro'&&(!referenciaId||!seleccion)){setError('Selecciona el documento relacionado con el caso.');return}setGuardando(true);setError('');const data=new FormData();data.append('referencia_tipo',tipoRef);data.append('referencia_id',referenciaId);data.append('asunto',asunto);data.append('categoria',categoria);data.append('descripcion',descripcion);data.append('prioridad',prioridad);archivos.forEach(f=>data.append('archivos',f));try{const r=await fetch(`${api}/tickets`,{method:'POST',headers:auth(),body:data});const d=await r.json();if(!r.ok)throw new Error(d.detail||'No se pudo crear el ticket.');setTickets(prev=>[d,...prev]);setAbierto(d.id);setAsunto('');setDescripcion('');setPrioridad('normal');setArchivos([]);setReferenciaId('');setCategoria('factura');form.reset()}catch(err){setError(err instanceof Error?err.message:'No se pudo crear el ticket.')}finally{setGuardando(false)}}
 async function responder(e:FormEvent){e.preventDefault();if(!abierto)return;setEnviandoMensaje(true);setError('');const data=new FormData();data.append('mensaje',mensaje);archivosMensaje.forEach(f=>data.append('archivos',f));try{const r=await fetch(`${api}/tickets/${abierto}/mensajes`,{method:'POST',headers:auth(),body:data});const d=await r.json();if(!r.ok)throw new Error(d.detail||'No se pudo enviar el mensaje.');setTickets(prev=>prev.map(t=>t.id===abierto?d:t));setMensaje('');setArchivosMensaje([])}catch(err){setError(err instanceof Error?err.message:'No se pudo enviar el mensaje.')}finally{setEnviandoMensaje(false)}}
 async function descargar(ticketId:string,adjunto:Adjunto){try{const r=await fetch(`${api}/tickets/${ticketId}/adjuntos/${adjunto.id}`,{headers:auth()});if(!r.ok)throw new Error('No se pudo descargar el archivo.');const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download=adjunto.nombre;a.click();URL.revokeObjectURL(url)}catch(e){setError(e instanceof Error?e.message:'No se pudo descargar el archivo.')}}
 const visibles=tickets.filter(t=>(filtro==='todos'||t.estado===filtro)&&(`${t.numero} ${t.asunto} ${t.referencia?.numero||''} ${t.estado}`).toLocaleLowerCase('es').includes(busqueda.trim().toLocaleLowerCase('es')))
 const abiertos=tickets.filter(t=>!['resuelto','cerrado'].includes(t.estado)).length
 return <main className={styles.page}>
  <header className={styles.header}><div><p className={styles.eyebrow}>COMUNICACIÓN CON COMPRAS</p><h1>Consultas y observaciones</h1><p>Reporta problemas de órdenes, facturas o documentos y consulta las respuestas.</p></div><button className={styles.refresh} onClick={()=>setRecarga(v=>v+1)} disabled={cargando}>Actualizar</button></header>
  <section className={styles.intro}><span className={styles.introIcon}>i</span><p>Al asociar un caso a una orden, el equipo de compras podrá identificar al responsable. El contacto directo se habilitará cuando los datos de compradores estén disponibles en la integración.</p></section>
  {error&&<div className={styles.error} role="alert">{error}<button type="button" onClick={()=>setError('')} aria-label="Cerrar mensaje">×</button></div>}
  <div className={styles.layout}>
   <section className={styles.panel}><div className={styles.panelHead}><div><h2>Crear un caso</h2><p>Indica el documento y explica qué necesitas.</p></div></div>
    <form className={styles.form} onSubmit={crear}>
     <label>Tipo de consulta<select value={categoria} onChange={e=>cambiarCategoria(e.target.value)}>{categorias.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
     {tipoRef!=='general'&&<label>{tipoTitulo[tipoRef]}<select required value={referenciaId} onChange={e=>setReferenciaId(e.target.value)}><option value="">Selecciona un documento</option>{opciones.map(r=><option key={r.id} value={r.id}>{r.numero}{r.pedido?` · Pedido ${r.pedido}`:''}{r.descripcion?` · ${r.descripcion}`:''}</option>)}</select>{opciones.length===0&&<small>No encontramos documentos de este tipo para tu empresa.</small>}</label>}
     {seleccion?.pedido&&<p className={styles.routeInfo}>Caso relacionado con pedido {seleccion.pedido}. El equipo de compras podrá ubicar al responsable de la orden.</p>}
     <label>Asunto<input required minLength={5} maxLength={200} value={asunto} onChange={e=>setAsunto(e.target.value)} placeholder="Ej.: Mi factura figura como observada"/></label>
     <label>Prioridad<select value={prioridad} onChange={e=>setPrioridad(e.target.value)}><option value="normal">Normal · consulta sin bloqueo operativo</option><option value="alta">Alta · operación detenida o vencimiento próximo</option></select></label>
     <label>Describe el problema<textarea required minLength={10} maxLength={5000} rows={5} value={descripcion} onChange={e=>setDescripcion(e.target.value)} placeholder="Incluye el mensaje de error, qué esperabas y cualquier dato que ayude a revisarlo."/></label>
     <label>Evidencia (opcional) · hasta 5 archivos<input type="file" accept=".pdf,.png,.jpg,.jpeg,.xml" multiple onChange={e=>tomarArchivos(e,'nuevo')}/><small>PDF, PNG, JPG o XML · máximo 5 MB por archivo y 20 MB por envío.</small></label>{archivos.length>0&&<p className={styles.fileList}>{archivos.map(f=>f.name).join(' · ')}</p>}
     <button className={styles.primary} disabled={guardando}>{guardando?'Enviando…':'Enviar consulta'}</button>
    </form>
   </section>
   <section className={styles.panel}><div className={styles.panelHead}><div><h2>Mis casos</h2><p>{abiertos} abiertos · {tickets.length} en total</p></div></div>
    <div className={styles.filters}><input type="search" placeholder="Buscar número o asunto" value={busqueda} onChange={e=>setBusqueda(e.target.value)}/><select value={filtro} onChange={e=>setFiltro(e.target.value)}><option value="todos">Todos los estados</option>{Object.entries(estadoLabel).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
    {cargando?<p className={styles.empty} role="status">Cargando tus casos…</p>:visibles.length===0?<div className={styles.empty}><h3>{tickets.length?'No hay casos con estos filtros':'Aún no tienes casos reportados'}</h3><p>Los casos enviados aparecerán aquí con su estado y conversación.</p></div>:<div className={styles.caseList}>{visibles.map(t=><article className={styles.case} key={t.id}><button type="button" className={styles.caseToggle} aria-expanded={abierto===t.id} onClick={()=>setAbierto(abierto===t.id?'':t.id)}><span className={styles.caseTop}><strong>{t.numero}</strong><span className={styles.priority} data-priority={t.prioridad}>{t.prioridad==='alta'?'Prioridad alta':'Normal'}</span><span className={styles.badge} data-state={t.estado}>{estadoLabel[t.estado]||t.estado}</span></span><span className={styles.caseSubject}>{t.asunto}</span><small>{t.referencia?`${tipoTitulo[t.referencia.tipo]||'Documento'} ${t.referencia.numero||''}`:'Consulta general'} · {fecha(t.creado_en)}</small></button>{abierto===t.id&&<div className={styles.conversation}><p><strong>Categoría:</strong> {categorias.find(([v])=>v===t.categoria)?.[1]||t.categoria}</p><div className={styles.messages}>{t.mensajes.map(m=><div className={styles.message} key={m.id}><div><strong>{m.autor_tipo==='proveedor'?'Tú':'Compras'}</strong><small>{fecha(m.creado_en)}</small></div><p>{m.mensaje}</p>{m.adjuntos.map(a=><button type="button" className={styles.attachment} key={a.id} onClick={()=>descargar(t.id,a)}>↓ {a.nombre}</button>)}</div>)}</div>{t.adjuntos.map(a=><button type="button" className={styles.attachment} key={a.id} onClick={()=>descargar(t.id,a)}>↓ {a.nombre}</button>)}{!['resuelto','cerrado'].includes(t.estado)&&<form className={styles.reply} onSubmit={responder}><label>Responder<textarea required minLength={2} maxLength={5000} value={abierto===t.id?mensaje:''} onChange={e=>setMensaje(e.target.value)} placeholder="Escribe una respuesta o agrega información…"/></label><label>Adjuntar evidencia<input type="file" accept=".pdf,.png,.jpg,.jpeg,.xml" multiple onChange={e=>tomarArchivos(e,'mensaje')}/></label>{archivosMensaje.length>0&&<small>{archivosMensaje.map(f=>f.name).join(' · ')}</small>}<button className={styles.primary} disabled={enviandoMensaje}>{enviandoMensaje?'Enviando…':'Enviar respuesta'}</button></form>}</div>}</article>)}</div>}
   </section>
  </div>
  <p className={styles.note}>Los casos se guardan en el portal con el documento relacionado y sus adjuntos. En esta etapa no se envían correos externos; el responsable se notificará cuando se conecte el directorio de compradores.</p>
 </main>
}
