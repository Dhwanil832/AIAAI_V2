import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getReport, toggleFlag, deleteReport } from '../api/reports'
import client from '../api/client'
import ThemeToggle from '../components/ThemeToggle'
import NotificationBell from '../components/NotificationBell'

const SEVERITY_COLORS = {
  low: 'text-green-400 bg-green-900/30 border-green-800',
  medium: 'text-yellow-400 bg-yellow-900/30 border-yellow-800',
  high: 'text-orange-400 bg-orange-900/30 border-orange-800',
  critical: 'text-red-400 bg-red-900/30 border-red-800',
}

const TYPE_COLORS = {
  'Personal Injuries': 'text-blue-400 bg-blue-900/30 border-blue-800',
  'Near Miss': 'text-purple-400 bg-purple-900/30 border-purple-800',
  'Equipment Damage': 'text-orange-400 bg-orange-900/30 border-orange-800',
}

const STATUS_COLORS = {
  submitted:       'text-gray-400 bg-gray-800 border-gray-700',
  under_review:    'text-yellow-400 bg-yellow-900/30 border-yellow-800',
  approved:        'text-green-400 bg-green-900/30 border-green-800',
  needs_more_info: 'text-orange-400 bg-orange-900/30 border-orange-800',
  closed:          'text-blue-400 bg-blue-900/30 border-blue-800',
}

const STATUS_LABELS = {
  submitted:       'Submitted',
  under_review:    'Under Review',
  approved:        'Approved',
  needs_more_info: 'Needs More Info',
  closed:          'Closed',
}

function Badge({ label, colorClass }) {
  return (
    <span className={`text-xs font-mono px-2 py-0.5 rounded border ${colorClass}`}>
      {label}
    </span>
  )
}

function Section({ title, fields }) {
  const entries = Object.entries(fields).filter(([, v]) => v)
  if (entries.length === 0) return null
  return (
    <div className="mb-6">
      <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-3 pb-2 border-b border-gray-800">
        {title}
      </div>
      <div className="space-y-2">
        {entries.map(([key, value]) => (
          <div key={key} className="flex gap-4">
            <div className="text-gray-500 text-xs font-mono w-40 shrink-0 pt-0.5">
              {key.replace(/_/g, ' ')}
            </div>
            <div className="text-gray-200 text-xs font-mono flex-1">{value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SimilarIncidentCard({ incident, onClick }) {
  const severityColor = {
    low: 'text-green-400', medium: 'text-yellow-400',
    high: 'text-orange-400', critical: 'text-red-400'
  }[incident.severity?.toLowerCase()] || 'text-gray-400'

  return (
    <div
      onClick={onClick}
      className="bg-gray-800 border border-gray-700 hover:border-orange-600 rounded-lg px-4 py-3 cursor-pointer transition-all group"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="text-gray-500 text-xs font-mono">
          {incident.source === 'submitted' ? `Report #${incident.source_id}` : `ID: ${incident.source_id || '—'}`}
        </span>
        {incident.source_file && incident.source !== 'submitted' && (
          <span className="text-gray-600 text-xs font-mono truncate max-w-[160px]">{incident.source_file}</span>
        )}
        <span className="ml-auto text-orange-500 text-xs font-mono">Score: {incident.score}</span>
        <span className="text-gray-600 text-xs font-mono group-hover:text-orange-400 transition-colors">↗</span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {incident.location && (
          <div className="text-xs font-mono">
            <span className="text-gray-600">Location: </span>
            <span className="text-gray-300">{incident.location}</span>
          </div>
        )}
        {incident.datetime && (
          <div className="text-xs font-mono">
            <span className="text-gray-600">Date: </span>
            <span className="text-gray-300">{incident.datetime}</span>
          </div>
        )}
        {incident.severity && (
          <div className="text-xs font-mono">
            <span className="text-gray-600">Severity: </span>
            <span className={severityColor}>{incident.severity}</span>
          </div>
        )}
        {incident.actions_taken && (
          <div className="text-xs font-mono">
            <span className="text-gray-600">Actions: </span>
            <span className="text-gray-300 truncate max-w-[200px] inline-block align-bottom">{incident.actions_taken}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function IncidentDetailModal({ incident, onClose }) {
  if (!incident) return null

  const fields = [
    { label: 'Source', value: incident.source === 'submitted' ? `Submitted Report #${incident.source_id}` : `Historical — ${incident.source_file}` },
    { label: 'Incident Type', value: incident.incident_type },
    { label: 'Date / Time', value: incident.datetime },
    { label: 'Shift', value: incident.shift },
    { label: 'Location', value: incident.location },
    { label: 'Department', value: incident.department },
    { label: 'Plant', value: incident.plant },
    { label: 'Person Involved', value: incident.person_involved },
    { label: 'Person Type', value: incident.person_type },
    { label: 'Severity', value: incident.severity },
    { label: 'SIF Case', value: incident.sif_case },
    { label: 'Accident Type', value: incident.accident_type },
    { label: 'Accident Agent', value: incident.accident_agent },
    { label: 'Injury Type', value: incident.injury_type },
    { label: 'Injury Agent', value: incident.injury_agent },
    { label: 'Life Saving Rules', value: incident.life_saving_rules },
    { label: 'Damage Amount', value: incident.damage_amount },
    { label: 'Activity Type', value: incident.activity_type },
    { label: 'Incident Activity', value: incident.incident_activity },
    { label: 'Incident Agent', value: incident.incident_agent },
    { label: 'Actions Taken', value: incident.actions_taken },
  ].filter(f => f.value)

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-lg max-h-[80vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div>
            <div className="text-white font-semibold text-sm">Similar Incident</div>
            <div className="text-gray-500 text-xs font-mono mt-0.5">Similarity score: {incident.score}</div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white text-xs font-mono transition-colors"
          >
            ✕ Close
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4 space-y-2">
          {fields.map(({ label, value }) => (
            <div key={label} className="flex gap-3 text-xs font-mono">
              <span className="text-gray-500 w-36 shrink-0">{label}</span>
              <span className="text-gray-200">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function ReportPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()

  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [selectedIncident, setSelectedIncident] = useState(null)

  // Review workflow state
  const [reviewNote, setReviewNote] = useState('')
  const [showNoteInput, setShowNoteInput] = useState(false)
  const [pendingStatus, setPendingStatus] = useState(null)
  const [reviewMsg, setReviewMsg] = useState(null)

  useEffect(() => {
    fetchReport()
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  const fetchReport = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getReport(id)
      setReport(data)
    } catch (e) {
      setError(e.response?.status === 404 ? 'Report not found.' : 'Failed to load report.')
    } finally {
      setLoading(false)
    }
  }

  const handleToggleFlag = async () => {
    setActionLoading(true)
    try {
      const updated = await toggleFlag(id)
      setReport(prev => ({
        ...prev,
        flagged: updated.flagged,
        flag_reason: updated.flag_reason
      }))
    } catch (e) {
      alert('Failed to update flag.')
    } finally {
      setActionLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setActionLoading(true)
    try {
      await deleteReport(id)
      navigate('/dashboard')
    } catch (e) {
      alert('Failed to delete report.')
      setActionLoading(false)
    }
  }

  const handleReview = async (status, note = null) => {
    setActionLoading(true)
    setReviewMsg(null)
    try {
      const updated = await client.patch(`/reports/${id}/review`, {
        status,
        review_note: note || reviewNote || null
      })
      setReport(prev => ({
        ...prev,
        status: updated.data.status,
        review_note: updated.data.review_note,
        reviewed_by: updated.data.reviewed_by,
        reviewed_at: updated.data.reviewed_at
      }))
      setReviewNote('')
      setShowNoteInput(false)
      setPendingStatus(null)
      setReviewMsg(`Status updated to: ${STATUS_LABELS[status]}`)
      setTimeout(() => setReviewMsg(null), 3000)
    } catch (e) {
      alert('Failed to update review status.')
    } finally {
      setActionLoading(false)
    }
  }

  const handleNeedsMoreInfo = () => {
    setPendingStatus('needs_more_info')
    setShowNoteInput(true)
  }

  const formatDate = (iso) => {
    if (!iso) return '—'
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    })
  }

  const incidentType = report?.report_json?.basic_info?.incident_type || ''

  const getSections = () => {
    if (!report?.report_json) return []
    const sections = []
    const basic = report.report_json.basic_info || {}
    sections.push({ title: 'Basic Information', fields: basic })

    if (incidentType === 'Personal Injuries' && report.report_json.injury_data) {
      sections.push({ title: 'Injury Details', fields: report.report_json.injury_data })
    } else if (incidentType === 'Near Miss' && report.report_json.near_miss_data) {
      sections.push({ title: 'Near Miss Details', fields: report.report_json.near_miss_data })
    } else if (incidentType === 'Equipment Damage' && report.report_json.equipment_damage_data) {
      sections.push({ title: 'Equipment Damage Details', fields: report.report_json.equipment_damage_data })
    }
    return sections
  }

  const getChatHistory = () => {
    if (!report?.context_document) return []
    const ctx = typeof report.context_document === 'string'
      ? JSON.parse(report.context_document)
      : report.context_document
    return ctx?.chat_history || []
  }

  const getSimilarIncidents = () => {
    if (!report?.similar_incidents) return []
    return Array.isArray(report.similar_incidents) ? report.similar_incidents : []
  }

  return (
    <div className="min-h-screen bg-gray-950 flex">

      {/* Sidebar */}
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
            onClick={() => navigate('/dashboard')}
            className="w-full text-left px-3 py-2 rounded text-sm font-mono text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
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
          <NotificationBell />
          <ThemeToggle />
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Header */}
        <div className="border-b border-gray-800 px-8 py-5 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="text-gray-500 hover:text-white text-sm font-mono transition-colors"
            >
              ← Back
            </button>
            {report && (
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-white font-semibold">Report #{report.id}</h1>
                {incidentType && (
                  <Badge
                    label={incidentType}
                    colorClass={TYPE_COLORS[incidentType] || 'text-gray-400 bg-gray-800 border-gray-700'}
                  />
                )}
                {report.report_json?.basic_info?.severity && (
                  <Badge
                    label={report.report_json.basic_info.severity}
                    colorClass={SEVERITY_COLORS[report.report_json.basic_info.severity?.toLowerCase()] || 'text-gray-400 bg-gray-800 border-gray-700'}
                  />
                )}
                {report.status && (
                  <Badge
                    label={STATUS_LABELS[report.status] || report.status}
                    colorClass={STATUS_COLORS[report.status] || 'text-gray-400 bg-gray-800 border-gray-700'}
                  />
                )}
                {report.flagged && (
                  <Badge label="Flagged" colorClass="text-red-400 bg-red-900/30 border-red-800" />
                )}
              </div>
            )}
          </div>

          {report && (
            <div className="text-right">
              <div className="text-gray-600 text-xs font-mono">Submitted by {report.creator_name}</div>
              <div className="text-gray-700 text-xs font-mono mt-0.5">{formatDate(report.created_at)}</div>
              {report.reviewed_by && (
                <div className="text-gray-700 text-xs font-mono mt-0.5">
                  Reviewed by {report.reviewed_by} · {formatDate(report.reviewed_at)}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Body */}
        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="flex gap-1">
              <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-red-400 font-mono text-sm">{error}</div>
          </div>
        ) : report ? (
          <div className="flex-1 flex overflow-hidden">

            {/* Left — structured report + similar incidents */}
            <div className="w-1/2 border-r border-gray-800 overflow-y-auto px-8 py-6">
              <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-5">
                Report Details
              </div>

              {getSections().map(({ title, fields }) => (
                <Section key={title} title={title} fields={fields} />
              ))}

              {/* Review note */}
              {report.review_note && (
                <div className={`mt-2 mb-6 p-3 rounded border ${
                  report.status === 'needs_more_info'
                    ? 'bg-orange-950/30 border-orange-900'
                    : report.status === 'approved'
                    ? 'bg-green-950/30 border-green-900'
                    : 'bg-gray-800 border-gray-700'
                }`}>
                  <div className="text-gray-500 text-xs font-mono mb-1">Review note</div>
                  <div className="text-gray-200 text-xs font-mono">{report.review_note}</div>
                </div>
              )}

              {report.flag_reason && (
                <div className="mt-2 mb-6 p-3 bg-red-950/30 border border-red-900 rounded">
                  <div className="text-red-400 text-xs font-mono">
                    <span className="text-red-600">Flag reason: </span>
                    {report.flag_reason}
                  </div>
                </div>
              )}

              {/* Similar incidents */}
              {getSimilarIncidents().length > 0 && (
                <div className="mt-2">
                  <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-3 pb-2 border-b border-gray-800">
                    Similar Past Incidents ({getSimilarIncidents().length})
                  </div>
                  <div className="space-y-3">
                    {getSimilarIncidents().map((incident, i) => (
                      <SimilarIncidentCard key={i} incident={incident} onClick={() => setSelectedIncident(incident)} />
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Right — chat history */}
            <div className="w-1/2 overflow-y-auto px-8 py-6">
              <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-5">
                Chat History
              </div>

              {getChatHistory().length === 0 ? (
                <div className="text-gray-700 text-xs font-mono">No chat history available.</div>
              ) : (
                <div className="space-y-3">
                  {getChatHistory().map((msg, i) => (
                    <div
                      key={i}
                      className={`flex ${msg.is_user ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-sm px-3 py-2 rounded text-xs font-mono leading-relaxed ${
                          msg.is_user
                            ? 'bg-orange-500/20 border border-orange-800 text-orange-200'
                            : 'bg-gray-800 border border-gray-700 text-gray-300'
                        }`}
                      >
                        {msg.content}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        ) : null}

        {/* Admin action bar */}
        {report && user?.role === 'admin' && (
          <div className="border-t border-gray-800 bg-gray-900">

            {/* Note input — shown when requesting more info */}
            {showNoteInput && (
              <div className="px-8 pt-4 pb-2 border-b border-gray-800">
                <div className="text-gray-500 text-xs font-mono mb-2">
                  Add a note for the reporter — explain what information is needed:
                </div>
                <div className="flex gap-3">
                  <input
                    type="text"
                    value={reviewNote}
                    onChange={e => setReviewNote(e.target.value)}
                    placeholder="e.g. Please provide the exact time and shift details..."
                    className="flex-1 bg-gray-800 border border-gray-700 text-white text-xs font-mono px-3 py-2 rounded focus:outline-none focus:border-orange-500 transition-colors"
                  />
                  <button
                    onClick={() => handleReview(pendingStatus, reviewNote)}
                    disabled={actionLoading}
                    className="bg-orange-500 hover:bg-orange-400 text-white text-xs font-mono px-4 py-2 rounded transition-colors disabled:opacity-50"
                  >
                    Send
                  </button>
                  <button
                    onClick={() => { setShowNoteInput(false); setReviewNote(''); setPendingStatus(null) }}
                    className="text-gray-500 hover:text-white text-xs font-mono px-3 py-2 rounded transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            <div className="px-8 py-4 flex items-center gap-4 flex-wrap">
              <span className="text-gray-600 text-xs font-mono uppercase tracking-wider">Admin Actions</span>

              {reviewMsg && (
                <span className="text-green-400 text-xs font-mono">{reviewMsg}</span>
              )}

              {/* Review status buttons */}
              <button
                onClick={() => handleReview('under_review')}
                disabled={actionLoading || report.status === 'under_review'}
                className="text-xs font-mono px-4 py-2 rounded border border-yellow-800 text-yellow-400 hover:bg-yellow-900/30 transition-colors disabled:opacity-30"
              >
                Mark Under Review
              </button>

              <button
                onClick={() => handleReview('approved')}
                disabled={actionLoading || report.status === 'approved'}
                className="text-xs font-mono px-4 py-2 rounded border border-green-800 text-green-400 hover:bg-green-900/30 transition-colors disabled:opacity-30"
              >
                Approve
              </button>

              <button
                onClick={handleNeedsMoreInfo}
                disabled={actionLoading || showNoteInput}
                className="text-xs font-mono px-4 py-2 rounded border border-orange-800 text-orange-400 hover:bg-orange-900/30 transition-colors disabled:opacity-30"
              >
                Request More Info
              </button>

              <button
                onClick={() => handleReview('closed')}
                disabled={actionLoading || report.status === 'closed'}
                className="text-xs font-mono px-4 py-2 rounded border border-blue-800 text-blue-400 hover:bg-blue-900/30 transition-colors disabled:opacity-30"
              >
                Close
              </button>

              <div className="ml-auto flex items-center gap-3">
                <button
                  onClick={handleToggleFlag}
                  disabled={actionLoading}
                  className={`text-xs font-mono px-4 py-2 rounded border transition-colors disabled:opacity-50 ${
                    report.flagged
                      ? 'border-gray-700 text-gray-400 hover:text-white hover:border-gray-500'
                      : 'border-red-800 text-red-400 hover:bg-red-900/30'
                  }`}
                >
                  {report.flagged ? 'Unflag' : 'Flag'}
                </button>

                <button
                  onClick={handleDelete}
                  disabled={actionLoading}
                  className={`text-xs font-mono px-4 py-2 rounded border transition-colors disabled:opacity-50 ${
                    confirmDelete
                      ? 'border-red-500 bg-red-900/50 text-red-300'
                      : 'border-gray-700 text-gray-500 hover:border-red-800 hover:text-red-400'
                  }`}
                >
                  {confirmDelete ? 'Confirm Delete' : 'Delete'}
                </button>

                {confirmDelete && (
                  <button
                    onClick={() => setConfirmDelete(false)}
                    className="text-xs font-mono text-gray-600 hover:text-gray-400 transition-colors"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

      </div>

      <IncidentDetailModal incident={selectedIncident} onClose={() => setSelectedIncident(null)} />
    </div>
  )
}