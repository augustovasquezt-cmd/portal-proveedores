'use client'

import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'

const menuItems = [
  { href: '/dashboard', label: 'Inicio', icon: '🏠' },
  { href: '/dashboard/ordenes', label: 'Ordenes de compra', icon: '📋' },
  { href: '/dashboard/facturas', label: 'Facturas', icon: '🧾' },
  { href: '/dashboard/pagos', label: 'Estado de pagos', icon: '💰' },
  { href: '/dashboard/certificados', label: 'Certificados', icon: '📜' },
  { href: '/dashboard/tickets', label: 'Tickets de soporte', icon: '🎫' },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [verificando, setVerificando] = useState(true)
  const [razonSocial, setRazonSocial] = useState('')

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      router.push('/')
      return
    }
    setRazonSocial(localStorage.getItem('razon_social') || '')
    setVerificando(false)
  }, [router])

  const cerrarSesion = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('ruc')
    localStorage.removeItem('razon_social')
    router.push('/')
  }

  if (verificando) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-400 text-sm">Verificando sesion...</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-900 rounded-lg flex items-center justify-center">
              <span className="text-white text-sm font-bold">P</span>
            </div>
            <span className="font-semibold text-gray-800 text-sm">Portal Proveedores</span>
          </div>
          <p className="text-xs text-gray-400 mt-2 truncate">{razonSocial}</p>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {menuItems.map(function (item) {
            const activo = pathname === item.href
            const clases = activo
              ? 'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors bg-blue-50 text-blue-900'
              : 'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors text-gray-600 hover:bg-gray-100'

            return (
              <a key={item.href} href={item.href} className={clases}>
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </a>
            )
          })}
        </nav>

        <div className="p-4 border-t border-gray-200">
          <button
            onClick={cerrarSesion}
            className="w-full text-left text-sm text-gray-500 hover:text-red-600 transition-colors px-3 py-2"
          >
            Cerrar sesion
          </button>
        </div>
      </aside>

      <main className="flex-1 p-8">{children}</main>
    </div>
  )
}
