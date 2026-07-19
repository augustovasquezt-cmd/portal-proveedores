'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function Home() {
  const router = useRouter()
  const [ruc, setRuc] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  const handleLogin = async () => {
    setError('')
    setCargando(true)
    const rucRegex = /^\d{11}$/
    if (!rucRegex.test(ruc)) {
      setError('El RUC debe tener exactamente 11 dígitos numéricos')
      setCargando(false)
      return
    }

    try {
      const res = await fetch('http://localhost:8000/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ruc, password }),
      })

      const data = await res.json()

      if (!res.ok) {
        setError(data.detail || 'Error al iniciar sesión')
        setCargando(false)
        return
      }

      // Guardamos el token y datos del proveedor
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('ruc', data.proveedor.ruc)
      localStorage.setItem('razon_social', data.proveedor.razon_social)

      router.push('/dashboard')
    } catch (err) {
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
          <p className="text-sm text-gray-500 mt-1">Ingresa con tu RUC y contraseña</p>
        </div>
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-600">RUC</label>
            <input
              type="text"
              placeholder="20xxxxxxxxx"
              value={ruc}
              onChange={(e) => setRuc(e.target.value)}
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-900"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-600">Contraseña</label>
            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-900"
            />
          </div>

          {error && (
            <p className="text-red-600 text-sm text-center">{error}</p>
          )}

          <button
            onClick={handleLogin}
            disabled={cargando}
            className="w-full bg-blue-900 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-800 transition-colors disabled:opacity-50"
          >
            {cargando ? 'Ingresando...' : 'Ingresar al portal'}
          </button>
        </div>
        <p className="text-center text-xs text-gray-400 mt-6">
          ¿Primera vez? <span className="text-blue-900 cursor-pointer">Solicita tu acceso aquí</span>
        </p>
      </div>
    </main>
  )
}
