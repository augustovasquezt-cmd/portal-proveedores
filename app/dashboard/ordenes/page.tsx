'use client'

import { useEffect, useState } from 'react'

type Orden = {
  id: string
  numero: string
  monto_total: number
  estado: string
  descripcion: string
  creado_en: string
}

const estadoColores: Record<string, string> = {
  por_recepcionar: 'bg-yellow-100 text-yellow-800',
  en_proceso: 'bg-blue-100 text-blue-800',
  entregado: 'bg-green-100 text-green-800',
  cancelado: 'bg-red-100 text-red-800',
}

export default function Ordenes() {
  const [ordenes, setOrdenes] = useState<Orden[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    async function cargarOrdenes() {
      const token = localStorage.getItem('token')
      try {
        const res = await fetch('http://localhost:8000/ordenes', {
          headers: { Authorization: 'Bearer ' + token },
        })
        if (!res.ok) {
          throw new Error('No se pudo cargar las ordenes')
        }
        const data = await res.json()
        setOrdenes(data)
      } catch (err) {
        setError('No se pudieron cargar las ordenes de compra')
      } finally {
        setCargando(false)
      }
    }
    cargarOrdenes()
  }, [])

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-800 mb-6">Ordenes de compra</h1>

      {cargando && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6">
          <p className="text-gray-400 text-sm">Cargando ordenes...</p>
        </div>
      )}

      {!cargando && error && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6">
          <p className="text-red-600 text-sm">{error}</p>
        </div>
      )}

      {!cargando && !error && ordenes.length === 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6">
          <p className="text-gray-500 text-sm">Aun no hay ordenes de compra registradas.</p>
        </div>
      )}

      {!cargando && !error && ordenes.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-6 py-3 font-medium text-gray-500">Numero</th>
                <th className="text-left px-6 py-3 font-medium text-gray-500">Descripcion</th>
                <th className="text-left px-6 py-3 font-medium text-gray-500">Monto</th>
                <th className="text-left px-6 py-3 font-medium text-gray-500">Estado</th>
                <th className="text-left px-6 py-3 font-medium text-gray-500">Fecha</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {ordenes.map(function (orden) {
                const colorEstado = estadoColores[orden.estado] || 'bg-gray-100 text-gray-800'
                const fecha = new Date(orden.creado_en).toLocaleDateString('es-PE')
                return (
                  <tr key={orden.id}>
                    <td className="px-6 py-4 font-medium text-gray-800">{orden.numero}</td>
                    <td className="px-6 py-4 text-gray-600">{orden.descripcion}</td>
                    <td className="px-6 py-4 text-gray-600">S/ {orden.monto_total.toFixed(2)}</td>
                    <td className="px-6 py-4">
                      <span className={"px-2 py-1 rounded-full text-xs font-medium " + colorEstado}>
                        {orden.estado.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-gray-500">{fecha}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
