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
  id: string;
  serie: string;
  correlativo: string;
  monto_subtotal: number;
  monto_igv: number;
  monto_total: number;
  estado: string;
  creado_en: string;
  lineas: FacturaLinea[];
}

export default function FacturaDetallePage() {
  const [factura, setFactura] = useState<Factura | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  useEffect(() => {
    const fetchFactura = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          router.push('/login');
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

  if (loading) return <div className="p-4">Cargando...</div>;
  if (error) return <div className="p-4 text-red-500">Error: {error}</div>;
  if (!factura) return <div className="p-4">Factura no encontrada</div>;

  return (
    <div className="p-6">
      <Link href="/dashboard/facturas" className="text-blue-600 hover:text-blue-800 mb-4 inline-block">
        ← Volver a Facturas
      </Link>

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
              {factura.lineas.map((linea) => (
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
              <span>IGV (18%):</span>
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
