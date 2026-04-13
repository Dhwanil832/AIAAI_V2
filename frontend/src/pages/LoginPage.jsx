import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api/auth'
import { useAuth } from '../context/AuthContext'
import ThemeToggle from '../components/ThemeToggle'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { loginUser } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await login(username, password)
      loginUser(data.access_token, data.user)
      navigate('/chat')
    } catch (err) {
      setError('Invalid username or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 bg-orange-500 rounded flex items-center justify-center">
              <span className="text-white font-bold text-sm">S</span>
            </div>
            <span className="text-orange-500 font-mono text-sm tracking-widest uppercase">Safety Chatbot</span>
          </div>
          <h1 className="text-white text-3xl font-bold tracking-tight">Sign in</h1>
          <p className="text-gray-500 text-sm mt-1">Incident reporting system</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-400 text-xs font-mono uppercase tracking-wider mb-2">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-gray-900 border border-gray-800 text-white px-4 py-3 rounded focus:outline-none focus:border-orange-500 transition-colors font-mono"
              placeholder="username"
              required
            />
          </div>
          <div>
            <label className="block text-gray-400 text-xs font-mono uppercase tracking-wider mb-2">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-gray-900 border border-gray-800 text-white px-4 py-3 rounded focus:outline-none focus:border-orange-500 transition-colors font-mono"
              placeholder="••••••••"
              required
            />
          </div>
          {error && (
            <div className="bg-red-950 border border-red-800 text-red-400 px-4 py-3 rounded text-sm font-mono">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-orange-500 hover:bg-orange-400 disabled:bg-orange-900 disabled:text-orange-700 text-white font-bold py-3 rounded transition-colors mt-2 tracking-wide"
          >
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
        <p className="text-gray-700 text-xs font-mono text-center mt-8">
          Contact your administrator to create an account
        </p>
        <ThemeToggle />
      </div>
    </div>
  )
}