'use client'

import { FormEvent, useState } from 'react'
import { useRouter } from 'next/navigation'

export default function ActualizarPassword() {
  const router = useRouter()
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [confirmacion, setConfirmacion] = useState('')
  const [error, setError] = useState('')
  const [guardando, setGuardando] = useState(false)

  async function cambiar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('')
    if (nueva.length < 12) { setError('La nueva contraseña debe tener al menos 12 caracteres.'); return }
    if (nueva !== confirmacion) { setError('La confirmación no coincide.'); return }
    setGuardando(true)
    try {
      const response = await fetch('http://localhost:8000/auth/cambiar-password', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ password_actual: actual, password_nueva: nueva }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'No se pudo cambiar la contraseña.')
      localStorage.setItem('access_token', result.access_token)
      localStorage.setItem('password_change_required', 'false')
      const role = localStorage.getItem('user_role')
      const clients = JSON.parse(localStorage.getItem('available_clients') || '[]')
      router.replace(role === 'proveedor' && !localStorage.getItem('client_id') && clients.length > 1 ? '/seleccionar-cliente' : role === 'administrador_ivs' ? '/dashboard/ivs/clientes' : '/dashboard')
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo cambiar la contraseña.') }
    finally { setGuardando(false) }
  }

  return <main className="flex min-h-screen items-center justify-center bg-slate-50 p-5"><form onSubmit={cambiar} className="w-full max-w-md space-y-4 rounded-2xl border border-slate-200 bg-white p-7 shadow-sm">
    <div><h1 className="text-2xl font-bold text-brand-navy">Actualiza tu contraseña</h1><p className="mt-2 text-sm text-brand-muted">Por seguridad, debes reemplazar la contraseña temporal antes de usar el portal.</p></div>
    <label className="block text-sm font-semibold text-brand-navy">Contraseña temporal o actual<input required type="password" autoComplete="current-password" value={actual} onChange={event => setActual(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal" /></label>
    <label className="block text-sm font-semibold text-brand-navy">Nueva contraseña<input required minLength={12} type="password" autoComplete="new-password" value={nueva} onChange={event => setNueva(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal" /></label>
    <label className="block text-sm font-semibold text-brand-navy">Confirma la nueva contraseña<input required minLength={12} type="password" autoComplete="new-password" value={confirmacion} onChange={event => setConfirmacion(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal" /></label>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <button disabled={guardando} className="w-full rounded-lg bg-brand-teal px-4 py-3 font-semibold text-white disabled:opacity-50">{guardando ? 'Guardando…' : 'Guardar nueva contraseña'}</button>
  </form></main>
}
