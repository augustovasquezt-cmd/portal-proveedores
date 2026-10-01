'use client'

import { useEffect, useState } from 'react'

type Profile = { id: string; usuario: string; nombre: string; rol: string }

export default function MisDatosPage() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const timer = window.setTimeout(() => fetch('http://localhost:8000/auth/me', { headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` } })
      .then(async response => { if (!response.ok) throw new Error('No se pudo cargar tu perfil.'); setProfile(await response.json()) })
      .catch(caught => setError(caught instanceof Error ? caught.message : 'Error al consultar el perfil.')), 0)
    return () => window.clearTimeout(timer)
  }, [])
  return <div className="mx-auto max-w-4xl space-y-6"><header><p className="text-sm font-semibold uppercase tracking-wide text-brand-teal">Cuenta interna</p><h1 className="mt-1 text-3xl font-bold text-brand-navy">Mis datos</h1><p className="mt-2 text-slate-600">Información de tu usuario y perfil de acceso.</p></header>{error && <p role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">{error}</p>}<section className="rounded-xl border border-slate-200 bg-white p-6">{!profile ? <p className="text-slate-500">Cargando perfil…</p> : <dl className="grid gap-5 sm:grid-cols-2">{[['Nombre',profile.nombre],['Usuario',profile.usuario],['Perfil',profile.rol === 'cuentas_por_pagar' ? 'Cuentas por pagar' : profile.rol],['Identificador',profile.id]].map(([label,value])=><div key={label}><dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 font-medium text-brand-navy">{value}</dd></div>)}</dl>}<p className="mt-6 rounded-lg bg-brand-soft p-4 text-sm text-slate-700">Para cambiar tu nombre, rol o contraseña, solicita la actualización al administrador del portal. El rol controla qué facturas y acciones puedes consultar.</p></section></div>
}
