'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';

interface FacturaLinea {
  id: number;
  numero_linea: number;
  descripcion: string;
  cantidad: number;
  precio_unitario: number;
  monto_subtotal: number;
  igv: number;
  monto_total: number;
}

interface Factura {
  sap?: {estado:string;documento:string|null}|null;
  id: string;
  serie: string;
  correlativo: string;
  monto_subtotal: number;
  monto_igv: number;
  monto_total: number;
  estado: string;
  creado_en: string;
  lineas: FacturaLinea[]; documentos_base: {tipo:string;numero:string;linea:string;cantidad:number}[]; adjuntos: boolean; tiene_xml: boolean; posiciones: {pedido:string;numero:string;material:string;cantidad:number;subtotal:number;igv:number;total:number}[]; fecha_emision: string | null; ruc_receptor: string | null;
}

export default function FacturaDetallePage() {
  const [factura, setFactura] = useState<Factura | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pdfPreview, setPdfPreview] = useState<{ facturaId: string; url: string } | null>(null);
  const [xmlPreview, setXmlPreview] = useState<{ facturaId: string; text: string } | null>(null);
  const [xmlLoading, setXmlLoading] = useState(false);
  const [showXml, setShowXml] = useState(false);
  const [attachmentError, setAttachmentError] = useState<{ facturaId: string; message: string } | null>(null);
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  useEffect(() => {
    const fetchFactura = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          router.push('/');
          return;
        }

        const response = await fetch(`http://localhost:8000/facturas/${id}`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          throw new Error('Factura no encontrada');
        }

        const data = await response.json();
        setFactura(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido');
      } finally {
        setLoading(false);
      }
    };

    fetchFactura();
  }, [id, router]);

  useEffect(() => {
    if (!factura?.adjuntos) return;
    const controller = new AbortController();
    let objectUrl = '';
    fetch(`http://localhost:8000/facturas/${factura.id}/archivos/pdf`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('No se pudo cargar la vista previa del PDF.');
        return response.blob();
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setPdfPreview({ facturaId: factura.id, url: objectUrl });
      })
      .catch((err) => {
        if (!controller.signal.aborted) setAttachmentError({ facturaId: factura.id, message: err instanceof Error ? err.message : 'Error al mostrar el PDF.' });
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [factura?.id, factura?.adjuntos]);

  async function verXml() {
    if (showXml) {
      setShowXml(false);
      return;
    }
    setShowXml(true);
    if (xmlPreview?.facturaId === id || !factura?.tiene_xml) return;
    setXmlLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/facturas/${id}/archivos/xml`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
      });
      if (!response.ok) throw new Error('No se pudo cargar la vista previa del XML.');
      setXmlPreview({ facturaId: id, text: await response.text() });
    } catch (err) {
      setAttachmentError({ facturaId: id, message: err instanceof Error ? err.message : 'Error al mostrar el XML.' });
    } finally {
      setXmlLoading(false);
    }
  }

  async function descargar(tipo: string) {
    try {
      const res = await fetch(`http://localhost:8000/facturas/${id}/archivos/${tipo}`, {headers: {Authorization: `Bearer ${localStorage.getItem('access_token')}`}});
      if (!res.ok) throw new Error('No se pudo descargar el archivo.');
      const url = URL.createObjectURL(await res.blob());
      const link = document.createElement('a'); link.href = url; link.download = `factura.${tipo}`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : 'Error de descarga'); }
  }
  if (loading) return <div className="p-4">Cargando...</div>;
  if (error) return <div className="p-4 text-red-500">Error: {error}</div>;
  if (!factura) return <div className="p-4">Factura no encontrada</div>;

  return (
    <div className="p-6">
      {factura.sap && <p role="status" className="bg-blue-50 p-4 mb-4 rounded-lg">Integración SAP: {factura.sap.estado === "pendiente_configuracion" ? "Factura validada y preparada. Pendiente de configurar conexión; no enviada a SAP." : factura.sap.estado}{factura.sap.documento && ` · Documento ${factura.sap.documento}`}</p>}
      {factura.estado === 'Pendiente de revisión' && <p role="status" className="bg-blue-50 text-blue-800 p-4 mb-4 rounded-lg">Factura registrada. Pendiente de revisión.</p>}
      {factura.adjuntos && <section className="bg-white rounded-lg border border-slate-200 p-5 mb-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h2 className="text-xl font-semibold">Archivos adjuntos</h2>
          <div className="flex flex-wrap gap-4">
            {factura.tiene_xml && <><button type="button" onClick={() => void verXml()} className="text-blue-700 underline">{showXml ? 'Ocultar XML' : 'Ver XML'}</button><button type="button" onClick={() => void descargar('xml')} className="text-blue-700 underline">Descargar XML</button></>}
            <button type="button" onClick={() => void descargar('pdf')} className="text-blue-700 underline">Descargar PDF</button>
          </div>
        </div>
        {attachmentError?.facturaId === factura.id && <p role="alert" className="mb-3 rounded bg-red-50 p-3 text-red-700">{attachmentError.message}</p>}
        <h3 className="mb-2 font-medium">Factura PDF</h3>
        {factura.adjuntos && pdfPreview?.facturaId !== factura.id && attachmentError?.facturaId !== factura.id && <p role="status" className="mb-3 text-slate-600">Cargando vista previa…</p>}
        {pdfPreview?.facturaId === factura.id && <iframe title={`Vista previa de factura ${factura.serie}-${factura.correlativo}`} src={pdfPreview.url} className="h-[min(78vh,900px)] min-h-[520px] w-full rounded border border-slate-300" />}
        {showXml && <div className="mt-6">
          <h3 className="mb-2 font-medium">XML original de la factura</h3>
          {xmlLoading ? <p role="status" className="text-slate-600">Cargando XML…</p> : xmlPreview?.facturaId === factura.id ? <pre className="max-h-[560px] overflow-auto whitespace-pre-wrap break-words rounded border border-slate-300 bg-slate-50 p-4 text-sm">{xmlPreview.text}</pre> : !factura.tiene_xml ? <p className="text-slate-600">No se adjuntó un XML a esta factura.</p> : null}
        </div>}
      </section>}
      {factura.fecha_emision && <p className="mb-4">Fecha de emisión: {factura.fecha_emision}</p>}
      {factura.ruc_receptor && <p className="mb-4">RUC de la sociedad receptora: {factura.ruc_receptor}</p>}
      <Link href="/dashboard/facturas" className="text-blue-600 hover:text-blue-800 mb-4 inline-block">
        ← Volver a Facturas
      </Link>

      {factura.documentos_base?.length > 0 && <div className="bg-white rounded-lg p-6 mb-6"><h2>Documentos de referencia</h2>{factura.documentos_base.map((d,i)=><p key={i}>{d.tipo} · {d.numero} / {d.linea} · Cantidad {d.cantidad}</p>)}</div>}
      {factura.posiciones?.length > 0 && <div className="bg-white rounded-lg p-6 mb-6"><h2>Posiciones facturadas</h2>{factura.posiciones.map(p => <p key={`${p.pedido}-${p.numero}`}>Pedido {p.pedido} · Posición {p.numero} · {p.material} · Cantidad {p.cantidad} · Total S/ {p.total.toFixed(2)}</p>)}</div>}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div>
            <p className="text-gray-600 text-sm">Serie</p>
            <p className="text-xl font-semibold">{factura.serie}</p>
          </div>
          <div>
            <p className="text-gray-600 text-sm">Correlativo</p>
            <p className="text-xl font-semibold">{factura.correlativo}</p>
          </div>
          <div>
            <p className="text-gray-600 text-sm">Estado</p>
            <p className={`text-lg font-semibold ${
              factura.estado === 'Pagada' ? 'text-green-600' :
              factura.estado === 'Vencida' ? 'text-red-600' :
              'text-blue-600'
            }`}>
              {factura.estado}
            </p>
          </div>
          <div>
            <p className="text-gray-600 text-sm">Fecha</p>
            <p className="text-lg font-semibold">{new Date(factura.creado_en).toLocaleDateString()}</p>
          </div>
        </div>
      </div>


      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-2xl font-bold mb-4">Líneas de Factura</h2>
        
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-100 border-b">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-semibold">Descripción</th>
                <th className="px-4 py-3 text-left text-sm font-semibold">Cantidad</th>
                <th className="px-4 py-3 text-left text-sm font-semibold">Precio Unitario</th>
                <th className="px-4 py-3 text-left text-sm font-semibold">Subtotal</th>
                <th className="px-4 py-3 text-left text-sm font-semibold">IGV</th>
                <th className="px-4 py-3 text-left text-sm font-semibold">Total</th>
              </tr>
            </thead>
            <tbody>
              {factura.lineas.length === 0 && <tr><td colSpan={6} className="px-4 py-4">Consulta el detalle de conceptos en el XML o PDF adjunto.</td></tr>}{factura.lineas.map((linea) => (
                <tr key={linea.id} className="border-b hover:bg-gray-50">
                  <td className="px-4 py-4">{linea.descripcion}</td>
                  <td className="px-4 py-4">{linea.cantidad}</td>
                  <td className="px-4 py-4">S/ {linea.precio_unitario.toFixed(2)}</td>
                  <td className="px-4 py-4">S/ {linea.monto_subtotal.toFixed(2)}</td>
                  <td className="px-4 py-4">S/ {linea.igv.toFixed(2)}</td>
                  <td className="px-4 py-4 font-semibold">S/ {linea.monto_total.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-6 flex justify-end">
          <div className="w-64">
            <div className="flex justify-between py-2 border-b">
              <span>Subtotal:</span>
              <span>S/ {factura.monto_subtotal.toFixed(2)}</span>
            </div>
            <div className="flex justify-between py-2 border-b">
              <span>Impuestos:</span>
              <span>S/ {factura.monto_igv.toFixed(2)}</span>
            </div>
            <div className="flex justify-between py-2 text-lg font-bold">
              <span>Total:</span>
              <span>S/ {factura.monto_total.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
