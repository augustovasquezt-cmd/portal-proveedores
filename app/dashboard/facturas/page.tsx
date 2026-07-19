'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

interface Factura {
  id: string;
  serie: string;
  correlativo: string;
  monto_total: number;
  estado: string;
  creado_en: string;
}

export default function FacturasPage() {
  const [facturas, setFacturas] = useState<Factura[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const router = useRouter();

  useEffect(() => {
    const fetchFacturas = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          router.push('/login');
          return;
        }

        const response = await fetch('http://localhost:8000/facturas', {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          throw new Error('Error al cargar facturas');
        }

        const data = await response.json();
        setFacturas(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido');
      } finally {
        setLoading(false);
      }
    };

    fetchFacturas();
  }, [router]);

  if (loading) return <div className="p-4">Cargando...</div>;
  if (error) return <div className="p-4 text-red-500">Error: {error}</div>;

  return (
    <div className="p-6">
      <h1 className="text-3xl font-bold mb-6">Facturas</h1>

      {facturas.length === 0 ? (
        <p className="text-gray-500">No hay facturas disponibles</p>
      ) : (
        <div className="overflow-x-auto bg-white rounded-lg shadow">
          <table className="w-full">
            <thead className="bg-gray-100 border-b">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold">Serie</th>
                <th className="px-6 py-3 text-left text-sm font-semibold">Correlativo</th>
                <th className="px-6 py-3 text-left text-sm font-semibold">Monto Total</th>
                <th className="px-6 py-3 text-left text-sm font-semibold">Estado</th>
                <th className="px-6 py-3 text-left text-sm font-semibold">Fecha</th>
                <th className="px-6 py-3 text-left text-sm font-semibold">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {facturas.map((factura) => (
                <tr key={factura.id} className="border-b hover:bg-gray-50">
                  <td className="px-6 py-4">{factura.serie}</td>
                  <td className="px-6 py-4">{factura.correlativo}</td>
                  <td className="px-6 py-4">S/ {factura.monto_total.toFixed(2)}</td>
                  <td className="px-6 py-4">
                    <span className={`px-3 py-1 rounded text-sm ${
                      factura.estado === 'Pagada' ? 'bg-green-100 text-green-800' :
                      factura.estado === 'Vencida' ? 'bg-red-100 text-red-800' :
                      'bg-blue-100 text-blue-800'
                    }`}>
                      {factura.estado}
                    </span>
                  </td>
                  <td className="px-6 py-4">{new Date(factura.creado_en).toLocaleDateString()}</td>
                  <td className="px-6 py-4">
                    <Link
                      href={`/dashboard/facturas/${factura.id}`}
                      className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                    >
                      Ver Detalle
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
