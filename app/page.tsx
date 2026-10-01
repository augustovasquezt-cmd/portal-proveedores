'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

export default function Home() {
  const router = useRouter()
  const [identificador, setIdentificador] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('sesion') === 'expirada') {
      const timer = window.setTimeout(() => setError('Tu sesión expiró por seguridad. Ingresa nuevamente para continuar.'), 0)
      return () => window.clearTimeout(timer)
    }
  }, [])

  const handleLogin = async () => {
    setError('')
    setCargando(true)
    const valor = identificador.trim()
    if (!valor) {
      setError('Ingresa tu RUC o correo corporativo.')
      setCargando(false)
      return
    }
    const esRuc = /^\d{11}$/.test(valor)

    try {
      const res = await fetch('http://localhost:8000/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(esRuc ? { ruc: valor, password } : { usuario: valor.toLowerCase(), password }),
      })

      const data = await res.json()

      if (!res.ok) {
        setError(typeof data.detail === 'string' ? data.detail : 'Usuario o contraseña incorrectos.')
        setCargando(false)
        return
      }

      // Guardamos el token y datos del proveedor
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('user_role', data.rol || 'proveedor')
      localStorage.setItem('password_change_required', data.debe_cambiar_password ? 'true' : 'false')
      if (data.clientes?.length) localStorage.setItem('available_clients', JSON.stringify(data.clientes))
      if (data.cliente_id) {
        localStorage.setItem('client_id', data.cliente_id)
        localStorage.setItem('client_name', data.clientes?.find((client: {id:string}) => client.id === data.cliente_id)?.nombre || '')
      } else localStorage.removeItem('client_id')
      if (data.proveedor) {
        localStorage.setItem('ruc', data.proveedor.ruc)
        localStorage.setItem('razon_social', data.proveedor.razon_social)
      } else {
        localStorage.removeItem('ruc')
        localStorage.setItem('razon_social', data.usuario.nombre)
      }

      router.push(data.debe_cambiar_password ? '/actualizar-password' : data.requiere_seleccion_cliente ? '/seleccionar-cliente' : data.rol === 'administrador_ivs' ? '/dashboard/ivs/clientes' : '/dashboard')
    } catch {
      setError('No se pudo conectar con el servidor')
      setCargando(false)
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8 w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="w-12 h-12 bg-blue-900 rounded-xl flex items-center justify-center mx-auto mb-4">
            <span className="text-white text-xl font-bold">P</span>
          </div>
          <h1 className="text-xl font-semibold text-gray-800">Portal de Proveedores</h1>
          <p className="text-sm text-gray-500 mt-1">Ingresa con tu RUC o correo corporativo</p>
        </div>
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-600">RUC o correo electrónico</label>
            <input
              type="text"
              autoComplete="username"
              placeholder="RUC de 11 dígitos o usuario@empresa.com"
              value={identificador}
              onChange={(e) => setIdentificador(e.target.value)}
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-teal"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-600">Contraseña</label>
            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-teal"
            />
          </div>

          {error && (
            <p className="text-red-600 text-sm text-center">{error}</p>
          )}

          <button
            onClick={handleLogin}
            disabled={cargando}
            className="w-full bg-brand-teal text-white rounded-lg py-2 text-sm font-medium hover:bg-brand-teal-hover transition-colors disabled:opacity-50"
          >
            {cargando ? 'Ingresando...' : 'Ingresar al portal'}
          </button>
        </div>
        <p className="text-center text-xs text-gray-400 mt-6">
          ¿Necesitas acceso? Contacta al administrador de tu empresa.
        </p>
      </div>
    </main>
  )
}
