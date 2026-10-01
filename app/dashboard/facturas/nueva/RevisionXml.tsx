import styles from './registro.module.css'
export type Revision = {
 cabecera:Record<string,string>;emisor:Record<string,string>;receptor:Record<string,string>;totales:Record<string,string>;
 lineas:Record<string,string>[];impuestos:Record<string,string>[];
 campos:{ruta:string;valor:string;atributos:Record<string,string>}[];
 validaciones:{campo:string;estado:string;detalle:string}[];
 pedido:{numero:string;total:number;facturado:number;saldo:number;moneda:string}|null;
 puede_enviar:boolean
}
function Fields({data}:{data:Record<string,string>}) {return <dl className={styles.grid}>{Object.entries(data).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value||'No informado'}</dd></div>)}</dl>}
function Rows({rows}:{rows:Record<string,string>[]}) {if(!rows.length)return <p>No informado en el XML.</p>;return <div className={styles.tableWrap}><table><thead><tr>{Object.keys(rows[0]).map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}>{Object.entries(r).map(([k,v])=><td key={k}>{v||'—'}</td>)}</tr>)}</tbody></table></div>}
export default function RevisionXml({revision}:{revision:Revision}) {return <div>
 <section><h2>3. Validación contra la orden de compra</h2>
 {revision.pedido&&<Fields data={{Orden:revision.pedido.numero,'Total del pedido':`S/ ${revision.pedido.total.toFixed(2)}`,'Ya facturado':`S/ ${revision.pedido.facturado.toFixed(2)}`,'Saldo disponible':`S/ ${revision.pedido.saldo.toFixed(2)}`}}/>}
 <ul className={styles.checks}>{revision.validaciones.map(v=><li key={v.campo} data-status={v.estado}><strong>{v.estado==='ok'?'✓ Conforme':v.estado==='error'?'✕ Revisar':'! No validado'} · {v.campo}</strong><span>{v.detalle}</span></li>)}</ul></section>
 <section><h2>4. Datos de la factura</h2><Fields data={revision.cabecera}/></section>
 <section><h2>Emisor</h2><Fields data={revision.emisor}/></section>
 <section><h2>Receptor</h2><Fields data={revision.receptor}/></section>
 <section><h2>Detalle de productos y servicios</h2><Rows rows={revision.lineas}/></section>
 <section><h2>Tributos</h2><Rows rows={revision.impuestos}/></section>
 <section><h2>Totales, descuentos y anticipos</h2><Fields data={revision.totales}/></section>
 <section><details><summary>Ver todos los campos y atributos del XML ({revision.campos.length})</summary><p>Incluye referencias, condiciones de pago, leyendas, extensiones y firma presentes en el archivo.</p><div className={styles.tableWrap}><table><thead><tr><th>Ruta XML</th><th>Valor</th><th>Atributos</th></tr></thead><tbody>{revision.campos.map((c,i)=><tr key={i}><td>{c.ruta}</td><td>{c.valor||'—'}</td><td>{Object.entries(c.atributos).map(([k,v])=><div key={k}>{k}: {v}</div>)}</td></tr>)}</tbody></table></div></details></section>
 </div>}
