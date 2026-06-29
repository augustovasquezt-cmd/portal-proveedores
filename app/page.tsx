export default function Home() {
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
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-900"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-600">Contraseña</label>
            <input
              type="password"
              placeholder="••••••••"
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-900"
            />
          </div>
          <button className="w-full bg-blue-900 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-800 transition-colors">
            Ingresar al portal
          </button>
        </div>
        <p className="text-center text-xs text-gray-400 mt-6">
          ¿Primera vez? <span className="text-blue-900 cursor-pointer">Solicita tu acceso aquí</span>
        </p>
      </div>
    </main>
  )
}