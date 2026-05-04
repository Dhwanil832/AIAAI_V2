import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { listReports } from '../api/reports'
import { listUnfinished, discardUnfinished } from '../api/unfinished'
import {
  getPendingWitnessRequests,
  getWitnessSubmissions,
  getWitnessView,
  submitWitnessAccount,
} from '../api/reports'
import client from '../api/client'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell
} from 'recharts'
import ThemeToggle from '../components/ThemeToggle'
import NotificationBell from '../components/NotificationBell'

const SEVERITY_COLORS = {
  low: 'text-green-400 bg-green-900/30 border-green-800',
  medium: 'text-yellow-400 bg-yellow-900/30 border-yellow-800',
  high: 'text-orange-400 bg-orange-900/30 border-orange-800',
  critical: 'text-red-400 bg-red-900/30 border-red-800',
}

const SEVERITY_BAR_COLORS = {
  low: '#4ade80',
  medium: '#facc15',
  high: '#fb923c',
  critical: '#f87171',
  unknown: '#4b5563',
}

const TYPE_COLORS = {
  'Personal Injuries': 'text-blue-400 bg-blue-900/30 border-blue-800',
  'Near Miss': 'text-purple-400 bg-purple-900/30 border-purple-800',
  'Equipment Damage': 'text-orange-400 bg-orange-900/30 border-orange-800',
}

const TYPE_BAR_COLORS = {
  'Personal Injuries': '#60a5fa',
  'Near Miss': '#c084fc',
  'Equipment Damage': '#fb923c',
}

function Badge({ label, colorClass }) {
  return (
    <span className={`text-xs font-mono px-2 py-0.5 rounded border ${colorClass}`}>
      {label}
    </span>
  )
}

function StatCard({ label, value, sub, valueColor }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg px-5 py-4">
      <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${valueColor || 'text-white'}`}>{value}</div>
      {sub && <div className="text-gray-600 text-xs font-mono mt-1">{sub}</div>}
    </div>
  )
}

function SectionTitle({ title }) {
  return (
    <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-3">
      {title}
    </div>
  )
}

// ── Witness Modal ─────────────────────────────────────────────────────────────
function WitnessModal({ reportId, onClose, onSubmitted }) {
  const [view, setView] = useState(null)       // witness-view data
  const [loading, setLoading] = useState(true)
  const [account, setAccount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [submitted, setSubmitted] = useState(false)

  useEffect(() => {
    const fetch = async () => {
      setLoading(true)
      try {
        const data = await getWitnessView(reportId)
        setView(data)
        if (data.my_nomination_status === 'submitted') setSubmitted(true)
      } catch (e) {
        setError('Failed to load incident details.')
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [reportId])

  const handleSubmit = async () => {
    if (!account.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await submitWitnessAccount(reportId, account.trim())
      setSubmitted(true)
      if (onSubmitted) onSubmitted(reportId)
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to submit account.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-lg max-h-[85vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div>
            <div className="text-white font-semibold text-sm">Witness Account</div>
            <div className="text-gray-500 text-xs font-mono mt-0.5">Report #{reportId}</div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white text-xs font-mono transition-colors"
          >
            ✕ Close
          </button>
        </div>

        <div className="overflow-y-auto px-5 py-4 flex-1">
          {loading ? (
            <div className="flex items-center justify-center py-10">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          ) : error && !view ? (
            <div className="text-red-400 text-xs font-mono">{error}</div>
          ) : view ? (
            <>
              {/* Identification — person / location / date only */}
              <div className="mb-4 p-3 bg-gray-800 border border-gray-700 rounded-lg">
                <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-2">Incident</div>
                <div className="space-y-1">
                  {view.identification?.person_involved && (
                    <div className="flex gap-3 text-xs font-mono">
                      <span className="text-gray-500 w-24 shrink-0">Person</span>
                      <span className="text-gray-200">{view.identification.person_involved}</span>
                    </div>
                  )}
                  {view.identification?.location && (
                    <div className="flex gap-3 text-xs font-mono">
                      <span className="text-gray-500 w-24 shrink-0">Location</span>
                      <span className="text-gray-200">{view.identification.location}</span>
                    </div>
                  )}
                  {view.identification?.datetime && (
                    <div className="flex gap-3 text-xs font-mono">
                      <span className="text-gray-500 w-24 shrink-0">Date / Time</span>
                      <span className="text-gray-200">{view.identification.datetime}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Collected fields from reporter */}
              <div className="mb-4">
                <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-2">
                  Collected Information
                </div>
                <div className="space-y-1">
                  {Object.entries(view.structured_fields || {}).map(([key, val]) =>
                    val ? (
                      <div key={key} className="flex gap-3 text-xs font-mono">
                        <span className="text-gray-500 w-24 shrink-0 capitalize">{key.replace(/_/g, ' ')}</span>
                        <span className="text-gray-200">{val}</span>
                      </div>
                    ) : null
                  )}
                </div>
              </div>

              {/* Account input or submitted view */}
              {submitted ? (
                <div>
                  <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-2">
                    Your Account
                  </div>
                  <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-3">
                    <p className="text-gray-300 text-xs font-mono leading-relaxed whitespace-pre-wrap">
                      {view.my_account || account}
                    </p>
                  </div>
                  <div className="text-green-400 text-xs font-mono mt-2">
                    ✓ Your account has been submitted
                  </div>
                </div>
              ) : (
                <div>
                  <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-2">
                    Your Account
                  </div>
                  <p className="text-gray-500 text-xs font-mono mb-2 leading-relaxed">
                    Please describe what you saw in your own words.
                  </p>
                  <textarea
                    value={account}
                    onChange={e => setAccount(e.target.value)}
                    placeholder="Describe what you witnessed..."
                    rows={5}
                    className="w-full bg-gray-800 border border-gray-700 text-white text-xs font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500 transition-colors resize-none"
                  />
                  {error && <div className="text-red-400 text-xs font-mono mt-1">{error}</div>}
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Footer — submit button, hidden once submitted */}
        {!loading && view && !submitted && (
          <div className="px-5 py-4 border-t border-gray-800 flex justify-end gap-3">
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-white text-xs font-mono px-4 py-2 rounded transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={submitting || !account.trim()}
              className="bg-orange-500 hover:bg-orange-400 text-white text-xs font-mono px-4 py-2 rounded transition-colors disabled:opacity-50"
            >
              {submitting ? 'Submitting...' : 'Submit Account'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const { user, logoutUser } = useAuth()
  const navigate = useNavigate()

  const [reports, setReports] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [unfinished, setUnfinished] = useState([])
  const [unfinishedLoading, setUnfinishedLoading] = useState(true)

  const [analytics, setAnalytics] = useState(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(true)

  // Witness state
  const [pendingWitness, setPendingWitness] = useState([])
  const [witnessSubmissions, setWitnessSubmissions] = useState([])
  const [witnessModalReportId, setWitnessModalReportId] = useState(null)

  // Filters
  const [filterType, setFilterType] = useState('')
  const [filterFlagged, setFilterFlagged] = useState(null)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')

  // Pagination
  const PAGE_SIZE = 10
  const [page, setPage] = useState(1)

  useEffect(() => {
    setPage(1)
  }, [filterType, filterFlagged, search]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchReports()
  }, [filterType, filterFlagged, search, page]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchUnfinished()
    fetchWitnessData()
    if (user?.role === 'admin') fetchAnalytics()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const fetchReports = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listReports({
        incident_type: filterType || null,
        flagged: filterFlagged,
        search: search || null,
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      })
      setReports(data.reports)
      setTotal(data.total)
    } catch (e) {
      setError('Failed to load reports.')
    } finally {
      setLoading(false)
    }
  }

  const fetchUnfinished = async () => {
    setUnfinishedLoading(true)
    try {
      const data = await listUnfinished()
      setUnfinished(data.unfinished)
    } catch (e) {
      console.error('Failed to load unfinished reports.')
    } finally {
      setUnfinishedLoading(false)
    }
  }

  const fetchAnalytics = async () => {
    setAnalyticsLoading(true)
    try {
      const res = await client.get('/dashboard/analytics')
      setAnalytics(res.data)
    } catch (e) {
      console.error('Failed to load analytics.')
    } finally {
      setAnalyticsLoading(false)
    }
  }

  const fetchWitnessData = async () => {
    try {
      const [pendingRes, submissionsRes] = await Promise.all([
        getPendingWitnessRequests(),
        getWitnessSubmissions(),
      ])
      setPendingWitness(pendingRes.pending || [])
      setWitnessSubmissions(submissionsRes.submissions || [])
    } catch (e) {
      // Non-critical — fail silently
    }
  }

  const handleDiscard = async (e, id) => {
    e.stopPropagation()
    try {
      await discardUnfinished(id)
      setUnfinished(prev => prev.filter(r => r.id !== id))
    } catch (e) {
      alert('Failed to discard report.')
    }
  }

  const handleResume = (report) => {
    const isSmartMode = report.report_json?._mode === 'smart'
    const url = isSmartMode
      ? `/chat?resume=${report.session_id}&resumeMode=smart&mode=smart`
      : `/chat?resume=${report.session_id}`
    navigate(url)
  }

  // After witness submits their account — move from pending to submissions
  const handleWitnessSubmitted = (reportId) => {
    setPendingWitness(prev => prev.filter(w => w.report_id !== reportId))
    fetchWitnessData()
  }

  const flaggedCount = reports.filter(r => r.flagged).length

  const formatDate = (iso) => {
    if (!iso) return '—'
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric'
    })
  }

  // Build chart data from analytics
  const typeChartData = analytics
    ? Object.entries(analytics.type_breakdown).map(([name, count]) => ({ name, count }))
    : []

  const severityChartData = analytics
    ? Object.entries(analytics.severity_breakdown)
      .sort((a, b) => {
        const order = ['low', 'medium', 'high', 'critical', 'unknown']
        return order.indexOf(a[0]) - order.indexOf(b[0])
      })
      .map(([name, count]) => ({ name, count }))
    : []

  const trendChartData = analytics ? analytics.monthly_trend : []

  return (
    <div className="min-h-screen bg-gray-950 flex">

      {/* Sidebar — UNCHANGED */}
      <div className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-orange-500 rounded flex items-center justify-center">
              <span className="text-white font-bold text-xs">S</span>
            </div>
            <span className="text-orange-500 font-mono text-xs tracking-widest uppercase">Safety</span>
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
            className="w-full text-left px-3 py-2 rounded text-sm font-mono bg-gray-800 text-white"
          >
            Dashboard
          </button>
          {user?.role === 'admin' && (
            <button
              onClick={() => navigate('/admin')}
              className="w-full text-left px-3 py-2 rounded text-sm font-mono text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
            >
              Admin
            </button>
          )}
        </nav>

        <div className="p-4 border-t border-gray-800">
          <div className="text-gray-500 text-xs font-mono mb-1">{user?.username}</div>
          <div className="text-gray-600 text-xs font-mono mb-3">{user?.job_title}</div>
          <NotificationBell onWitnessClick={(reportId) => setWitnessModalReportId(reportId)} />
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

        {/* Header — UNCHANGED */}
        <div className="border-b border-gray-800 px-8 py-5">
          <h1 className="text-white font-semibold text-lg">Reports Dashboard</h1>
          <p className="text-gray-500 text-xs font-mono mt-0.5">
            {user?.role === 'admin' ? 'All submitted reports' : 'Your submitted reports'}
          </p>
        </div>

        <div className="flex-1 overflow-y-auto px-8 py-6 space-y-8">

          {/* ── Admin only: Overview + Analytics — UNCHANGED ── */}
          {user?.role === 'admin' && (
            <>
              <div>
                <SectionTitle title="Overview" />
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <StatCard label="Total Reports" value={analytics?.total ?? total} />
                  <StatCard label="Flagged" value={analytics?.flagged ?? flaggedCount} sub="require attention" valueColor="text-red-400" />
                  <StatCard label="SIF Cases" value={analytics?.sif_cases ?? 0} sub="serious injury potential" valueColor={analytics?.sif_cases > 0 ? 'text-red-400' : 'text-white'} />
                  <StatCard label="In Progress" value={unfinished.length} sub="unfinished reports" valueColor="text-yellow-400" />
                </div>
              </div>

              {!analyticsLoading && analytics && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
                    <SectionTitle title="By Incident Type" />
                    {typeChartData.length === 0 ? (
                      <div className="text-gray-700 text-xs font-mono">No data</div>
                    ) : (
                      <ResponsiveContainer width="100%" height={160}>
                        <BarChart data={typeChartData} layout="vertical" margin={{ left: 0, right: 20 }}>
                          <XAxis type="number" hide />
                          <YAxis type="category" dataKey="name" width={110} tick={{ fill: '#6b7280', fontSize: 10, fontFamily: 'monospace' }} tickLine={false} axisLine={false} />
                          <Tooltip contentStyle={{ background: '#111318', border: '1px solid #1e2330', borderRadius: 4 }} labelStyle={{ color: '#9ca3af', fontSize: 11 }} itemStyle={{ color: '#e5e7eb', fontSize: 11 }} />
                          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                            {typeChartData.map((entry, i) => <Cell key={i} fill={TYPE_BAR_COLORS[entry.name] || '#6b7280'} />)}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                  <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
                    <SectionTitle title="By Severity" />
                    {severityChartData.length === 0 ? (
                      <div className="text-gray-700 text-xs font-mono">No data</div>
                    ) : (
                      <ResponsiveContainer width="100%" height={160}>
                        <BarChart data={severityChartData} layout="vertical" margin={{ left: 0, right: 20 }}>
                          <XAxis type="number" hide />
                          <YAxis type="category" dataKey="name" width={60} tick={{ fill: '#6b7280', fontSize: 10, fontFamily: 'monospace' }} tickLine={false} axisLine={false} />
                          <Tooltip contentStyle={{ background: '#111318', border: '1px solid #1e2330', borderRadius: 4 }} labelStyle={{ color: '#9ca3af', fontSize: 11 }} itemStyle={{ color: '#e5e7eb', fontSize: 11 }} />
                          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                            {severityChartData.map((entry, i) => <Cell key={i} fill={SEVERITY_BAR_COLORS[entry.name] || '#6b7280'} />)}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                  <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
                    <SectionTitle title="Monthly Trend" />
                    {trendChartData.length === 0 ? (
                      <div className="text-gray-700 text-xs font-mono">No data</div>
                    ) : (
                      <ResponsiveContainer width="100%" height={160}>
                        <BarChart data={trendChartData} margin={{ left: 0, right: 10 }}>
                          <XAxis dataKey="month" tick={{ fill: '#6b7280', fontSize: 9, fontFamily: 'monospace' }} tickLine={false} axisLine={false} />
                          <YAxis allowDecimals={false} tick={{ fill: '#6b7280', fontSize: 10, fontFamily: 'monospace' }} tickLine={false} axisLine={false} width={20} />
                          <Tooltip contentStyle={{ background: '#111318', border: '1px solid #1e2330', borderRadius: 4 }} labelStyle={{ color: '#9ca3af', fontSize: 11 }} itemStyle={{ color: '#e5e7eb', fontSize: 11 }} />
                          <Bar dataKey="count" fill="#f97316" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                </div>
              )}

              {!analyticsLoading && analytics && analytics.top_locations.length > 0 && (
                <div>
                  <SectionTitle title="Top Locations" />
                  <div className="bg-gray-900 border border-gray-800 rounded-lg divide-y divide-gray-800">
                    {analytics.top_locations.map((item, i) => {
                      const max = analytics.top_locations[0].count
                      const pct = Math.round((item.count / max) * 100)
                      return (
                        <div key={i} className="px-5 py-3 flex items-center gap-4">
                          <div className="text-gray-600 text-xs font-mono w-4 shrink-0">{i + 1}</div>
                          <div className="text-gray-300 text-xs font-mono w-32 shrink-0 truncate">{item.location}</div>
                          <div className="flex-1 bg-gray-800 rounded-full h-1.5">
                            <div className="bg-orange-500 h-1.5 rounded-full transition-all" style={{ width: `${pct}%` }} />
                          </div>
                          <div className="text-orange-400 text-xs font-mono w-8 text-right shrink-0">{item.count}</div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </>
          )}

          {/* ── Pending Witness Requests — visible to all roles ── */}
          {pendingWitness.length > 0 && (
            <div>
              <SectionTitle title={`Pending Witness Requests — ${pendingWitness.length}`} />
              <div className="space-y-2">
                {pendingWitness.map((w, i) => (
                  <div
                    key={i}
                    className="bg-gray-900 border border-yellow-900/50 rounded-lg px-5 py-3 flex items-center justify-between gap-4"
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      {w.incident_type && (
                        <Badge
                          label={w.incident_type}
                          colorClass={TYPE_COLORS[w.incident_type] || 'text-gray-400 bg-gray-800 border-gray-700'}
                        />
                      )}
                      <div className="flex gap-4 text-xs font-mono">
                        {w.person_involved && (
                          <span>
                            <span className="text-gray-600">Person: </span>
                            <span className="text-gray-400">{w.person_involved}</span>
                          </span>
                        )}
                        {w.location && (
                          <span>
                            <span className="text-gray-600">Location: </span>
                            <span className="text-gray-400">{w.location}</span>
                          </span>
                        )}
                        {w.datetime && (
                          <span>
                            <span className="text-gray-600">Date: </span>
                            <span className="text-gray-400">{w.datetime}</span>
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => setWitnessModalReportId(w.report_id)}
                      className="text-xs font-mono px-3 py-1.5 rounded border border-yellow-800 text-yellow-400 hover:bg-yellow-900/30 transition-colors shrink-0"
                    >
                      Submit Account
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Witness Submissions — visible to all roles ── */}
          {witnessSubmissions.length > 0 && (
            <div>
              <SectionTitle title={`Witness Submissions — ${witnessSubmissions.length}`} />
              <div className="space-y-2">
                {witnessSubmissions.map((w, i) => (
                  <div
                    key={i}
                    onClick={() => setWitnessModalReportId(w.report_id)}
                    className="bg-gray-900 border border-gray-800 hover:border-gray-600 rounded-lg px-5 py-3 flex items-center justify-between gap-4 cursor-pointer group"
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      {w.incident_type && (
                        <Badge
                          label={w.incident_type}
                          colorClass={TYPE_COLORS[w.incident_type] || 'text-gray-400 bg-gray-800 border-gray-700'}
                        />
                      )}
                      <Badge label="Submitted" colorClass="text-green-400 bg-green-900/30 border-green-800" />
                      <div className="flex gap-4 text-xs font-mono">
                        {w.person_involved && (
                          <span>
                            <span className="text-gray-600">Person: </span>
                            <span className="text-gray-400">{w.person_involved}</span>
                          </span>
                        )}
                        {w.location && (
                          <span>
                            <span className="text-gray-600">Location: </span>
                            <span className="text-gray-400">{w.location}</span>
                          </span>
                        )}
                      </div>
                    </div>
                    <span className="text-gray-700 text-xs font-mono shrink-0 group-hover:text-orange-400 transition-colors">
                      View →
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Unfinished reports — UNCHANGED ── */}
          {!unfinishedLoading && unfinished.length > 0 && (
            <div>
              <SectionTitle title={`Unfinished Reports — ${unfinished.length} in progress`} />
              <div className="space-y-2">
                {unfinished.map(report => (
                  <div
                    key={report.id}
                    className="bg-gray-900 border border-gray-700 border-dashed rounded-lg px-5 py-3 flex items-center justify-between gap-4"
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      {report.incident_type && (
                        <Badge
                          label={report.incident_type}
                          colorClass={TYPE_COLORS[report.incident_type] || 'text-gray-400 bg-gray-800 border-gray-700'}
                        />
                      )}
                      <div className="flex gap-4 text-xs font-mono">
                        {report.person_involved && (
                          <span>
                            <span className="text-gray-600">Person: </span>
                            <span className="text-gray-400">{report.person_involved}</span>
                          </span>
                        )}
                        {report.location && (
                          <span>
                            <span className="text-gray-600">Location: </span>
                            <span className="text-gray-400">{report.location}</span>
                          </span>
                        )}
                        {!report.person_involved && !report.location && (
                          <span className="text-gray-600">No details yet</span>
                        )}
                      </div>
                      <span className="text-gray-700 text-xs font-mono shrink-0">
                        {formatDate(report.updated_at)}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => handleResume(report)}
                        className="text-xs font-mono px-3 py-1.5 rounded border border-orange-800 text-orange-400 hover:bg-orange-900/30 transition-colors"
                      >
                        Resume
                      </button>
                      <button
                        onClick={(e) => handleDiscard(e, report.id)}
                        className="text-xs font-mono px-3 py-1.5 rounded border border-gray-700 text-gray-500 hover:border-red-800 hover:text-red-400 transition-colors"
                      >
                        Discard
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Filters + All Reports — UNCHANGED ── */}
          <div>
            <SectionTitle title="All Reports" />
            <div className="flex flex-wrap gap-3 items-center mb-4">

              <div className="flex gap-2">
                <input
                  type="text"
                  value={searchInput}
                  onChange={e => setSearchInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') setSearch(searchInput) }}
                  placeholder="Search person, location, ID..."
                  className="bg-gray-900 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500 transition-colors w-56"
                />
                <button
                  onClick={() => setSearch(searchInput)}
                  className="bg-gray-800 hover:bg-gray-700 border border-gray-700 text-white text-xs font-mono px-3 py-2 rounded transition-colors"
                >
                  Search
                </button>
              </div>

              <select
                value={filterType}
                onChange={e => setFilterType(e.target.value)}
                className="bg-gray-900 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500 transition-colors"
              >
                <option value="">All Types</option>
                <option value="Personal Injuries">Personal Injuries</option>
                <option value="Near Miss">Near Miss</option>
                <option value="Equipment Damage">Equipment Damage</option>
              </select>

              <select
                value={filterFlagged === null ? '' : String(filterFlagged)}
                onChange={e => setFilterFlagged(e.target.value === '' ? null : e.target.value === 'true')}
                className="bg-gray-900 border border-gray-700 text-white text-sm font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500 transition-colors"
              >
                <option value="">All Reports</option>
                <option value="true">Flagged Only</option>
                <option value="false">Not Flagged</option>
              </select>

              {(filterType || filterFlagged !== null || search) && (
                <button
                  onClick={() => { setFilterType(''); setFilterFlagged(null); setSearch(''); setSearchInput('') }}
                  className="text-gray-500 hover:text-white text-xs font-mono transition-colors"
                >
                  Clear filters
                </button>
              )}

              <span className="text-gray-600 text-xs font-mono ml-auto">
                {total} result{total !== 1 ? 's' : ''}
              </span>
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-20">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            ) : error ? (
              <div className="text-red-400 font-mono text-sm">{error}</div>
            ) : reports.length === 0 ? (
              <div className="text-center py-20">
                <div className="text-gray-600 font-mono text-sm">No reports found</div>
                <button
                  onClick={() => navigate('/chat')}
                  className="mt-4 text-orange-500 hover:text-orange-400 text-sm font-mono transition-colors"
                >
                  + File a new report
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {reports.map(report => (
                  <div
                    key={report.id}
                    onClick={() => navigate(`/reports/${report.id}`)}
                    className="bg-gray-900 border border-gray-800 hover:border-gray-600 rounded-lg px-5 py-4 cursor-pointer transition-all group"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-2">
                          <span className="text-gray-500 text-xs font-mono">#{report.id}</span>
                          {report.incident_type && (
                            <Badge
                              label={report.incident_type}
                              colorClass={TYPE_COLORS[report.incident_type] || 'text-gray-400 bg-gray-800 border-gray-700'}
                            />
                          )}
                          {report.severity && (
                            <Badge
                              label={report.severity}
                              colorClass={SEVERITY_COLORS[report.severity?.toLowerCase()] || 'text-gray-400 bg-gray-800 border-gray-700'}
                            />
                          )}
                          {report.flagged && (
                            <Badge label="Flagged" colorClass="text-red-400 bg-red-900/30 border-red-800" />
                          )}
                        </div>
                        <div className="flex flex-wrap gap-x-6 gap-y-1">
                          {report.report_json?.basic_info?.person_involved && (
                            <div className="text-xs font-mono">
                              <span className="text-gray-600">Person: </span>
                              <span className="text-gray-300">{report.report_json.basic_info.person_involved}</span>
                            </div>
                          )}
                          {report.location && (
                            <div className="text-xs font-mono">
                              <span className="text-gray-600">Location: </span>
                              <span className="text-gray-300">{report.location}</span>
                            </div>
                          )}
                          {report.datetime && (
                            <div className="text-xs font-mono">
                              <span className="text-gray-600">Incident date: </span>
                              <span className="text-gray-300">{report.datetime}</span>
                            </div>
                          )}
                          {report.flag_reason && (
                            <div className="text-xs font-mono">
                              <span className="text-gray-600">Flag reason: </span>
                              <span className="text-red-400">{report.flag_reason}</span>
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-gray-600 text-xs font-mono">{formatDate(report.created_at)}</div>
                        <div className="text-gray-700 text-xs font-mono mt-1">{report.creator_name}</div>
                        {report.vision_thread_status && (
                          <div
                            className={`text-xs font-mono mt-1 ${report.vision_thread_status === 'resolved' ? 'text-green-500' :
                                report.vision_thread_status === 'open' ? 'text-amber-500' :
                                  'text-gray-600'
                              }`}
                            title={`Photo follow-up: ${report.vision_thread_status}`}
                          >
                            📷
                          </div>
                        )}
                        <div className="text-orange-500 text-xs font-mono mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          View →
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!loading && total > PAGE_SIZE && (
              <div className="flex items-center justify-between mt-4">
                <span className="text-gray-600 text-xs font-mono">
                  Page {page} of {Math.ceil(total / PAGE_SIZE)}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="bg-gray-900 border border-gray-700 text-gray-400 hover:text-white text-xs font-mono px-3 py-1.5 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    ← Prev
                  </button>
                  <button
                    onClick={() => setPage(p => Math.min(Math.ceil(total / PAGE_SIZE), p + 1))}
                    disabled={page >= Math.ceil(total / PAGE_SIZE)}
                    className="bg-gray-900 border border-gray-700 text-gray-400 hover:text-white text-xs font-mono px-3 py-1.5 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Next →
                  </button>
                </div>
              </div>
            )}
          </div>

        </div>
      </div>

      {/* Witness modal — mounts when witnessModalReportId is set */}
      {witnessModalReportId && (
        <WitnessModal
          reportId={witnessModalReportId}
          onClose={() => setWitnessModalReportId(null)}
          onSubmitted={handleWitnessSubmitted}
        />
      )}
    </div>
  )
}