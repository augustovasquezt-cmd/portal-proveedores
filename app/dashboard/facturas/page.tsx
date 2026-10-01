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
  const [estadoFiltro, setEstadoFiltro] = useState('todas');

  useEffect(() => {
    const parametro = new URLSearchParams(window.location.search).get('estado');
    const filtroTimer = window.setTimeout(() => {
      if (parametro && ['revision','correccion','aprobadas','pagadas'].includes(parametro)) setEstadoFiltro(parametro);
    }, 0);
    const fetchFacturas = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          router.push('/');
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
    return () => window.clearTimeout(filtroTimer);
  }, [router]);

  const estadoNormalizado = (estado: string) => estado.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const filtradas = facturas.filter((factura) => {
    const estado = estadoNormalizado(factura.estado);
    if (estadoFiltro === 'revision') return estado.includes('revision');
    if (estadoFiltro === 'correccion') return estado.includes('rechaz') || estado.includes('observad') || estado.includes('correccion');
    if (estadoFiltro === 'aprobadas') return (estado.includes('aprob') || estado.includes('aceptad')) && !estado.includes('pagad');
    if (estadoFiltro === 'pagadas') return estado.includes('pagad');
    return true;
  });

  if (loading) return <div className="p-4">Cargando...</div>;
  if (error) return <div className="p-4 text-red-500">Error: {error}</div>;

  return (
    <div className="p-6">
      <h1 className="text-3xl font-bold mb-6">Facturas</h1><label className="block mb-5 max-w-sm text-sm font-medium">Estado<select className="block w-full mt-2 rounded-lg border border-slate-300 bg-white p-2" value={estadoFiltro} onChange={e => setEstadoFiltro(e.target.value)}><option value="todas">Todas las facturas</option><option value="revision">En revisión</option><option value="correccion">Requieren corrección</option><option value="aprobadas">Aprobadas pendientes de pago</option><option value="pagadas">Pagadas</option></select></label><Link href="/dashboard/facturas/nueva" className="inline-block bg-brand-teal text-white rounded-lg px-4 py-2 mb-6">Nueva factura</Link>

      {filtradas.length === 0 ? (
        <p className="text-gray-500">{facturas.length === 0 ? 'No hay facturas disponibles' : 'No hay facturas para este estado'}</p>
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
              {filtradas.map((factura) => (
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
