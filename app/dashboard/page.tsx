'use client'

import { useEffect, useState } from 'react'

export default function Dashboard() {
  const [razonSocial, setRazonSocial] = useState('')
  const [ruc, setRuc] = useState('')

  useEffect(() => {
    setRazonSocial(localStorage.getItem('razon_social') || '')
    setRuc(localStorage.getItem('ruc') || '')
  }, [])

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-800 mb-1">
        Bienvenido, {razonSocial}
      </h1>
      <p className="text-sm text-gray-500 mb-8">RUC: {ruc}</p>

      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <p className="text-gray-500 text-sm">
          Aquí verás un resumen de tus órdenes de compra, facturas pendientes y notificaciones recientes.
        </p>
      </div>
    </div>
  )
}