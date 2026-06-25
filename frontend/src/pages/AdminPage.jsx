import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { uploadHistorical, getHistoricalStats } from '../api/historical'
import { listUsers, createUser, updateUser, resetPassword, deleteUser } from '../api/users'
import { exportReports } from '../api/reports'
import ThemeToggle from '../components/ThemeToggle'
import NotificationBell from '../components/NotificationBell'

const INCIDENT_TYPES = [
  'Personal Injuries',
  'Near Miss',
  'Equipment Damage',
]

function UploadSection({ incidentType, onUploadComplete }) {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleFileChange = (e) => {
    setFile(e.target.files[0])
    setResult(null)
    setError(null)
  }

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setResult(null)
    setError(null)
    try {
      const data = await uploadHistorical(file, incidentType)
      setResult(data)
      setFile(null)
      onUploadComplete()
    } catch (e) {
      setError(e.response?.data?.detail || 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
      <div className="text-white text-sm font-semibold mb-1">{incidentType}</div>
      <div className="text-gray-500 text-xs font-mono mb-4">
        Upload .xls or .xlsx file — duplicates are skipped automatically
      </div>

      <div className="flex items-center gap-3">
        <label className="flex-1">
          <div className="bg-gray-800 border border-gray-700 hover:border-orange-500 rounded px-4 py-2 text-xs font-mono text-gray-400 cursor-pointer transition-colors truncate">
            {file ? file.name : 'Choose file...'}
          </div>
          <input
            type="file"
            accept=".xls,.xlsx"
            onChange={handleFileChange}
            className="hidden"
          />
        </label>
        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="bg-orange-500 hover:bg-orange-400 disabled:bg-gray-800 disabled:text-gray-600 text-white text-xs font-mono px-4 py-2 rounded transition-colors shrink-0"
        >
          {uploading ? 'Uploading...' : 'Upload'}
        </button>
      </div>

      {result && (
        <div className="mt-3 p-3 bg-green-900/20 border border-green-800 rounded text-xs font-mono">
          <div className="text-green-400 mb-1">✓ Upload complete</div>
          <div className="text-gray-400">
            <span className="text-white">{result.imported}</span> records imported
            {result.skipped > 0 && (
              <span className="text-gray-500"> · {result.skipped} duplicates skipped</span>
            )}
            <span className="text-gray-600"> · {result.total_rows} total rows in file</span>
          </div>
        </div>
      )}

      {error && (
        <div className="mt-3 p-3 bg-red-900/20 border border-red-800 rounded text-xs font-mono text-red-400">
          {error}
        </div>
      )}
    </div>
  )
}

export default function AdminPage() {
  const { user, logoutUser } = useAuth()
  const navigate = useNavigate()

  const [stats, setStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(true)

  const [users, setUsers] = useState([])
  const [usersLoading, setUsersLoading] = useState(true)
  const [editingUser, setEditingUser] = useState(null)
  const [editFields, setEditFields] = useState({})
  const [resetUserId, setResetUserId] = useState(null)
  const [newPassword, setNewPassword] = useState('')
  const [userActionMsg, setUserActionMsg] = useState(null)

  // Add user modal state
  const [showAddUser, setShowAddUser] = useState(false)
  const [newUserFields, setNewUserFields] = useState({
    username: '', password: '', email: '', job_title: '', role: 'user'
  })

  // Export state
  const [exportDateRange, setExportDateRange] = useState('all')
  const [exportIncidentType, setExportIncidentType] = useState('')
  const [exportLocation, setExportLocation] = useState('')
  const [exportFlagged, setExportFlagged] = useState('')
  const [exportLoading, setExportLoading] = useState(false)
  const [exportMsg, setExportMsg] = useState(null)

  useEffect(() => {
    fetchStats()
    fetchUsers()
  }, [])

  const fetchUsers = async () => {
    setUsersLoading(true)
    try {
      const data = await listUsers()
      setUsers(data.users)
    } catch (e) {
      console.error('Failed to load users')
    } finally {
      setUsersLoading(false)
    }
  }

  const showMsg = (msg, isError = false) => {
    setUserActionMsg({ msg, isError })
    setTimeout(() => setUserActionMsg(null), 3000)
  }

  const handleAddUser = async () => {
    if (!newUserFields.username.trim()) {
      showMsg('Username is required', true); return
    }
    if (!newUserFields.password || newUserFields.password.length < 6) {
      showMsg('Password must be at least 6 characters', true); return
    }
    try {
      await createUser({
        username: newUserFields.username.trim(),
        password: newUserFields.password,
        email: newUserFields.email || null,
        job_title: newUserFields.job_title || null,
        role: newUserFields.role,
      })
      setShowAddUser(false)
      setNewUserFields({ username: '', password: '', email: '', job_title: '', role: 'user' })
      fetchUsers()
      showMsg('User created successfully')
    } catch (e) {
      showMsg(e.response?.data?.detail || 'Failed to create user', true)
    }
  }

  const handleEditSave = async () => {
    try {
      await updateUser(editingUser.id, editFields)
      setEditingUser(null)
      setEditFields({})
      fetchUsers()
      showMsg('User updated successfully')
    } catch (e) {
      showMsg(e.response?.data?.detail || 'Update failed', true)
    }
  }

  const handleToggleActive = async (u) => {
    try {
      await updateUser(u.id, { is_active: !u.is_active })
      fetchUsers()
      showMsg(`User ${u.is_active ? 'deactivated' : 'activated'}`)
    } catch (e) {
      showMsg(e.response?.data?.detail || 'Action failed', true)
    }
  }

  const handleResetPassword = async () => {
    if (!newPassword || newPassword.length < 6) {
      showMsg('Password must be at least 6 characters', true)
      return
    }
    try {
      await resetPassword(resetUserId, newPassword)
      setResetUserId(null)
      setNewPassword('')
      showMsg('Password reset successfully')
    } catch (e) {
      showMsg(e.response?.data?.detail || 'Reset failed', true)
    }
  }

  const handleDelete = async (u) => {
    if (!window.confirm(`Delete user "${u.username}"? This cannot be undone.`)) return
    try {
      await deleteUser(u.id)
      fetchUsers()
      showMsg(`User "${u.username}" deleted`)
    } catch (e) {
      showMsg(e.response?.data?.detail || 'Delete failed', true)
    }
  }

  const fetchStats = async () => {
    setStatsLoading(true)
    try {
      const data = await getHistoricalStats()
      setStats(data)
    } catch (e) {
      console.error('Failed to load stats')
    } finally {
      setStatsLoading(false)
    }
  }

  const handleExport = async (format) => {
    setExportLoading(true)
    setExportMsg(null)
    try {
      await exportReports({
        format,
        date_range: exportDateRange,
        incident_type: exportIncidentType || null,
        location: exportLocation || null,
        flagged: exportFlagged === '' ? null : exportFlagged === 'true',
      })
      setExportMsg(`${format.toUpperCase()} exported successfully`)
      setTimeout(() => setExportMsg(null), 3000)
    } catch (e) {
      setExportMsg('Export failed')
      setTimeout(() => setExportMsg(null), 3000)
    } finally {
      setExportLoading(false)
    }
  }

  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="min-h-screen w-full bg-gray-950 flex overflow-hidden">

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-30 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'flex' : 'hidden'} md:flex w-64 bg-gray-900 border-r border-gray-800 flex-col fixed md:relative inset-y-0 left-0 z-40 md:z-auto`}>
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 bg-orange-500 rounded flex items-center justify-center">
                <span className="text-white font-bold text-xs">S</span>
              </div>
              <span className="text-orange-500 font-mono text-xs tracking-widest uppercase">Safety</span>
            </div>
            <button
              onClick={() => setSidebarOpen(false)}
              className="md:hidden text-gray-500 hover:text-white text-lg leading-none"
            >
              ✕
            </button>
          </div>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          <button
            onClick={() => navigate('/chat')}
            className="w-full text-left px-3 py-2 rounded text-sm font-mono text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
          >
            + New Report
          </button>
          <button
            onClick={() => navigate('/chat?mode=smart')}
            className="w-full text-left px-3 py-2 rounded text-sm font-mono text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
          >
            ✦ Smart Report
          </button>
          <button
            onClick={() => navigate('/dashboard')}
            className="w-full text-left px-3 py-2 rounded text-sm font-mono text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
          >
            Dashboard
          </button>
          <button
            onClick={() => navigate('/admin')}
            className="w-full text-left px-3 py-2 rounded text-sm font-mono bg-gray-800 text-white"
          >
            Admin
          </button>
        </nav>

        <div className="p-4 border-t border-gray-800">
          <div className="text-gray-500 text-xs font-mono mb-1">{user?.username}</div>
          <div className="text-gray-600 text-xs font-mono mb-3">{user?.job_title}</div>
          <NotificationBell />
          <ThemeToggle />
          <button
            onClick={logoutUser}
            className="text-gray-500 hover:text-red-400 text-xs font-mono transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Header */}
        <div className="border-b border-gray-800 px-4 md:px-8 py-5 flex items-center gap-3">
          <button
            onClick={() => setSidebarOpen(true)}
            className="md:hidden text-gray-400 hover:text-white text-xl leading-none"
          >
            ☰
          </button>
          <div>
            <h1 className="text-white font-semibold text-lg">Admin Panel</h1>
            <p className="text-gray-500 text-xs font-mono mt-0.5">
              Manage historical incident data and system settings
            </p>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-8">

          {/* Historical data stats */}
          <div>
            <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-4">
              Historical Incident Database
            </div>
            {statsLoading ? (
              <div className="text-gray-600 text-xs font-mono">Loading stats...</div>
            ) : stats ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div className="bg-gray-900 border border-gray-800 rounded-lg px-5 py-4">
                  <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-1">Total Records</div>
                  <div className="text-white text-2xl font-bold font-mono">{stats.total}</div>
                </div>
                <div className="bg-gray-900 border border-gray-800 rounded-lg px-5 py-4">
                  <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-1">Personal Injuries</div>
                  <div className="text-blue-400 text-2xl font-bold font-mono">{stats['Personal Injuries']}</div>
                </div>
                <div className="bg-gray-900 border border-gray-800 rounded-lg px-5 py-4">
                  <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-1">Near Miss</div>
                  <div className="text-purple-400 text-2xl font-bold font-mono">{stats['Near Miss']}</div>
                </div>
                <div className="bg-gray-900 border border-gray-800 rounded-lg px-5 py-4">
                  <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-1">Equipment Damage</div>
                  <div className="text-orange-400 text-2xl font-bold font-mono">{stats['Equipment Damage']}</div>
                </div>
              </div>
            ) : null}
          </div>

          {/* Upload sections */}
          <div>
            <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-4">
              Upload Historical Data
            </div>
            <div className="space-y-4">
              {INCIDENT_TYPES.map(type => (
                <UploadSection
                  key={type}
                  incidentType={type}
                  onUploadComplete={fetchStats}
                />
              ))}
            </div>
          </div>

          {/* User management */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="text-gray-500 text-xs font-mono uppercase tracking-wider">
                User Management
              </div>
              <div className="flex items-center gap-3">
                {userActionMsg && (
                  <span className={`text-xs font-mono ${userActionMsg.isError ? 'text-red-400' : 'text-green-400'}`}>
                    {userActionMsg.msg}
                  </span>
                )}
                <button
                  onClick={() => setShowAddUser(true)}
                  className="bg-orange-500 hover:bg-orange-400 text-white text-xs font-mono px-3 py-1.5 rounded transition-colors"
                >
                  + Add User
                </button>
              </div>
            </div>

            {usersLoading ? (
              <div className="text-gray-600 text-xs font-mono">Loading users...</div>
            ) : (
              <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="border-b border-gray-800 text-gray-500 uppercase tracking-wider">
                      <th className="text-left px-4 py-3">Username</th>
                      <th className="text-left px-4 py-3">Job Title</th>
                      <th className="text-left px-4 py-3">Role</th>
                      <th className="text-left px-4 py-3">Status</th>
                      <th className="text-left px-4 py-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} className="border-b border-gray-800 last:border-0 hover:bg-gray-800/50">
                        <td className="px-4 py-3 text-white">{u.username}</td>
                        <td className="px-4 py-3 text-gray-400">{u.job_title || '—'}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs ${u.role === 'admin' ? 'bg-orange-900/40 text-orange-400' : 'bg-gray-800 text-gray-400'}`}>
                            {u.role}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs ${u.is_active ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
                            {u.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <button
                              onClick={() => { setEditingUser(u); setEditFields({ email: u.email || '', job_title: u.job_title || '', role: u.role }) }}
                              className="text-gray-400 hover:text-white transition-colors"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => setResetUserId(u.id)}
                              className="text-gray-400 hover:text-blue-400 transition-colors"
                            >
                              Reset PW
                            </button>
                            <button
                              onClick={() => handleToggleActive(u)}
                              className={`transition-colors ${u.is_active ? 'text-gray-400 hover:text-yellow-400' : 'text-gray-400 hover:text-green-400'}`}
                            >
                              {u.is_active ? 'Deactivate' : 'Activate'}
                            </button>
                            {u.id !== user?.id && (
                              <button
                                onClick={() => handleDelete(u)}
                                className="text-gray-400 hover:text-red-400 transition-colors"
                              >
                                Delete
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Export Reports */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="text-gray-500 text-xs font-mono uppercase tracking-wider">
                Export Reports
              </div>
              {exportMsg && (
                <span className={`text-xs font-mono ${exportMsg.includes('failed') ? 'text-red-400' : 'text-green-400'}`}>
                  {exportMsg}
                </span>
              )}
            </div>

            <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">

                {/* Date Range */}
                <div>
                  <label className="text-gray-500 text-xs font-mono block mb-1">Date Range</label>
                  <select
                    value={exportDateRange}
                    onChange={e => setExportDateRange(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 text-white text-xs font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500 transition-colors"
                  >
                    <option value="all">All Time</option>
                    <option value="30d">Last 30 Days</option>
                    <option value="3m">Last 3 Months</option>
                    <option value="6m">Last 6 Months</option>
                    <option value="1y">Last Year</option>
                  </select>
                </div>

                {/* Incident Type */}
                <div>
                  <label className="text-gray-500 text-xs font-mono block mb-1">Incident Type</label>
                  <select
                    value={exportIncidentType}
                    onChange={e => setExportIncidentType(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 text-white text-xs font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500 transition-colors"
                  >
                    <option value="">All Types</option>
                    <option value="Personal Injuries">Personal Injuries</option>
                    <option value="Near Miss">Near Miss</option>
                    <option value="Equipment Damage">Equipment Damage</option>
                  </select>
                </div>

                {/* Location */}
                <div>
                  <label className="text-gray-500 text-xs font-mono block mb-1">Location</label>
                  <input
                    type="text"
                    value={exportLocation}
                    onChange={e => setExportLocation(e.target.value)}
                    placeholder="e.g. rolling mill"
                    className="w-full bg-gray-800 border border-gray-700 text-white text-xs font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500 transition-colors"
                  />
                </div>

                {/* Flagged */}
                <div>
                  <label className="text-gray-500 text-xs font-mono block mb-1">Flagged</label>
                  <select
                    value={exportFlagged}
                    onChange={e => setExportFlagged(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 text-white text-xs font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500 transition-colors"
                  >
                    <option value="">All Reports</option>
                    <option value="true">Flagged Only</option>
                    <option value="false">Not Flagged</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleExport('json')}
                  disabled={exportLoading}
                  className="bg-orange-500 hover:bg-orange-400 disabled:opacity-50 text-white text-xs font-mono px-4 py-2 rounded transition-colors"
                >
                  {exportLoading ? 'Exporting...' : '↓ Export JSON'}
                </button>
                <button
                  onClick={() => handleExport('csv')}
                  disabled={exportLoading}
                  className="bg-gray-800 hover:bg-gray-700 disabled:opacity-50 border border-gray-700 text-white text-xs font-mono px-4 py-2 rounded transition-colors"
                >
                  {exportLoading ? 'Exporting...' : '↓ Export CSV'}
                </button>
                <span className="text-gray-600 text-xs font-mono">
                  JSON includes full context · CSV is flat and Excel-friendly
                </span>
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* Add user modal */}
      {showAddUser && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-full max-w-md">
            <h2 className="text-white font-semibold mb-4">Add New User</h2>
            <div className="space-y-3">
              <div>
                <label className="text-gray-500 text-xs font-mono block mb-1">Username *</label>
                <input
                  type="text"
                  value={newUserFields.username}
                  onChange={e => setNewUserFields(f => ({ ...f, username: e.target.value }))}
                  placeholder="e.g. jsmith"
                  className="w-full bg-gray-800 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500"
                />
              </div>
              <div>
                <label className="text-gray-500 text-xs font-mono block mb-1">Password * (min 6 chars)</label>
                <input
                  type="password"
                  value={newUserFields.password}
                  onChange={e => setNewUserFields(f => ({ ...f, password: e.target.value }))}
                  placeholder="Initial password"
                  className="w-full bg-gray-800 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500"
                />
              </div>
              <div>
                <label className="text-gray-500 text-xs font-mono block mb-1">Job Title</label>
                <input
                  type="text"
                  value={newUserFields.job_title}
                  onChange={e => setNewUserFields(f => ({ ...f, job_title: e.target.value }))}
                  placeholder="e.g. Safety Officer"
                  className="w-full bg-gray-800 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500"
                />
              </div>
              <div>
                <label className="text-gray-500 text-xs font-mono block mb-1">Email</label>
                <input
                  type="text"
                  value={newUserFields.email}
                  onChange={e => setNewUserFields(f => ({ ...f, email: e.target.value }))}
                  placeholder="optional"
                  className="w-full bg-gray-800 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500"
                />
              </div>
              <div>
                <label className="text-gray-500 text-xs font-mono block mb-1">Role</label>
                <select
                  value={newUserFields.role}
                  onChange={e => setNewUserFields(f => ({ ...f, role: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500"
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </div>
            </div>
            <div className="flex gap-3 mt-5">
              <button
                onClick={handleAddUser}
                className="bg-orange-500 hover:bg-orange-400 text-white text-sm font-mono px-4 py-2 rounded transition-colors"
              >
                Create User
              </button>
              <button
                onClick={() => {
                  setShowAddUser(false)
                  setNewUserFields({ username: '', password: '', email: '', job_title: '', role: 'user' })
                }}
                className="bg-gray-800 hover:bg-gray-700 text-white text-sm font-mono px-4 py-2 rounded transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit user modal */}
      {editingUser && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-full max-w-md">
            <h2 className="text-white font-semibold mb-4">Edit — {editingUser.username}</h2>
            <div className="space-y-3">
              <div>
                <label className="text-gray-500 text-xs font-mono block mb-1">Email</label>
                <input
                  type="text"
                  value={editFields.email}
                  onChange={e => setEditFields(f => ({ ...f, email: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500"
                />
              </div>
              <div>
                <label className="text-gray-500 text-xs font-mono block mb-1">Job Title</label>
                <input
                  type="text"
                  value={editFields.job_title}
                  onChange={e => setEditFields(f => ({ ...f, job_title: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500"
                />
              </div>
              <div>
                <label className="text-gray-500 text-xs font-mono block mb-1">Role</label>
                <select
                  value={editFields.role}
                  onChange={e => setEditFields(f => ({ ...f, role: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500"
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </div>
            </div>
            <div className="flex gap-3 mt-5">
              <button
                onClick={handleEditSave}
                className="bg-orange-500 hover:bg-orange-400 text-white text-sm font-mono px-4 py-2 rounded transition-colors"
              >
                Save
              </button>
              <button
                onClick={() => { setEditingUser(null); setEditFields({}) }}
                className="bg-gray-800 hover:bg-gray-700 text-white text-sm font-mono px-4 py-2 rounded transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reset password modal */}
      {resetUserId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-full max-w-sm">
            <h2 className="text-white font-semibold mb-4">Reset Password</h2>
            <input
              type="password"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              placeholder="New password (min 6 chars)"
              className="w-full bg-gray-800 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500 mb-4"
            />
            <div className="flex gap-3">
              <button
                onClick={handleResetPassword}
                className="bg-orange-500 hover:bg-orange-400 text-white text-sm font-mono px-4 py-2 rounded transition-colors"
              >
                Reset
              </button>
              <button
                onClick={() => { setResetUserId(null); setNewPassword('') }}
                className="bg-gray-800 hover:bg-gray-700 text-white text-sm font-mono px-4 py-2 rounded transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}