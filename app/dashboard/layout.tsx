'use client'

import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'

const supplierMenuItems = [
  { href: '/dashboard', label: 'Inicio', icon: '🏠' },
  { href: '/dashboard/ordenes', label: 'Ordenes de compra', icon: '📋' },
  { href: '/dashboard/facturas', label: 'Facturas', icon: '🧾' },
  { href: '/dashboard/pagos', label: 'Estado de pagos', icon: '💰' },
  { href: '/dashboard/certificados', label: 'Retenciones', icon: '📜' },
  { href: '/dashboard/tickets', label: 'Consultas y observaciones', icon: '🎫' },
]

const apMenuItems = [
  { href: '/dashboard/cuentas-por-pagar/inicio', label: 'Inicio', icon: '🏠' },
  { href: '/dashboard/cuentas-por-pagar/comprobantes', label: 'Mis comprobantes', icon: '🧾' },
  { href: '/dashboard/cuentas-por-pagar/carga-masiva-oc', label: 'Carga masiva con OC', icon: '📊' },
  { href: '/dashboard/cuentas-por-pagar/sin-oc', label: 'Facturas sin OC/OS', icon: '📥' },
  { href: '/dashboard/cuentas-por-pagar/datos-maestros', label: 'Datos maestros', icon: '🏢' },
  { href: '/dashboard/cuentas-por-pagar/mis-datos', label: 'Mis datos', icon: '👤' },
  { href: '/dashboard/cuentas-por-pagar/mis-solicitudes', label: 'Mis solicitudes', icon: '📨' },
]

const adminMenuItems = [
  { href: '/dashboard/administracion/usuarios', label: 'Usuarios y proveedores', icon: '👥' },
]

const ivsMenuItems = [
  { href: '/dashboard/ivs/clientes', label: 'Clientes, cupos y sociedades', icon: '🏢' },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [verificando, setVerificando] = useState(true)
  const [razonSocial, setRazonSocial] = useState('')
  const [rol, setRol] = useState('proveedor')

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      router.push('/')
      return
    }
    const timer = window.setTimeout(() => {
      setRazonSocial(localStorage.getItem('client_name') || localStorage.getItem('razon_social') || '')
      const currentRole = localStorage.getItem('user_role') || 'proveedor'
      setRol(currentRole)
      if (localStorage.getItem('password_change_required') === 'true') {
        router.replace('/actualizar-password')
        return
      }
      if (currentRole === 'proveedor' && !localStorage.getItem('client_id')) {
        try { if (JSON.parse(localStorage.getItem('available_clients') || '[]').length > 1) { router.replace('/seleccionar-cliente'); return } } catch { /* corrupted cache is handled by login */ }
      }
      if (currentRole === 'administrador_ivs') {
        if (!pathname.startsWith('/dashboard/ivs')) { router.replace('/dashboard/ivs/clientes'); return }
      } else if (currentRole === 'administrador') {
        if (pathname !== '/dashboard/administracion/usuarios') { router.replace('/dashboard/administracion/usuarios'); return }
      } else if (currentRole === 'cuentas_por_pagar') {
        if (pathname === '/dashboard/cuentas-por-pagar') { router.replace('/dashboard/cuentas-por-pagar/inicio'); return }
        else if (!pathname.startsWith('/dashboard/cuentas-por-pagar')) { router.replace('/dashboard/cuentas-por-pagar'); return }
      } else if (pathname.startsWith('/dashboard/ivs') || pathname.startsWith('/dashboard/cuentas-por-pagar') || pathname.startsWith('/dashboard/administracion')) {
        router.replace('/dashboard')
        return
      }
      setVerificando(false)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [router, pathname])

  const cerrarSesion = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('ruc')
    localStorage.removeItem('razon_social')
    localStorage.removeItem('user_role')
    localStorage.removeItem('access_token')
    localStorage.removeItem('password_change_required')
    localStorage.removeItem('client_id')
    localStorage.removeItem('client_name')
    localStorage.removeItem('available_clients')
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
          <span className="font-semibold text-gray-800 text-sm">{rol === 'administrador_ivs' ? 'IVS · Administración SaaS' : rol === 'administrador' ? 'Portal · Administración' : rol === 'cuentas_por_pagar' ? 'Portal · Cuentas por pagar' : 'Portal Proveedores'}</span>
          </div>
          <p className="text-xs text-gray-400 mt-2 truncate">{razonSocial}</p>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {(rol === 'administrador_ivs' ? ivsMenuItems : rol === 'administrador' ? adminMenuItems : rol === 'cuentas_por_pagar' ? apMenuItems : supplierMenuItems).map(function (item) {
            const activo = pathname === item.href
            const clases = activo
              ? 'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors bg-brand-soft text-brand-teal shadow-[inset_0_-2px_0_#008c9c]'
              : 'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors text-brand-navy hover:bg-brand-soft'

            return (
              <a key={item.href} href={item.href} aria-current={activo ? 'page' : undefined} className={clases}>
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
