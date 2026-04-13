import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import {
  startChat, sendMessage, saveProgress, resumeChat,
  startSmartChat, sendSmartMessage, saveSmartProgress, resumeSmartChat
} from '../api/chat'
import ThemeToggle from '../components/ThemeToggle'
import NotificationBell from '../components/NotificationBell'

const TYPE_COLORS = {
  'Personal Injuries': 'text-blue-400 bg-blue-900/30 border-blue-800',
  'Near Miss': 'text-purple-400 bg-purple-900/30 border-purple-800',
  'Equipment Damage': 'text-orange-400 bg-orange-900/30 border-orange-800',
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

function renderMarkdown(text) {
  if (!text) return { __html: '' }
  const html = text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>')
  return { __html: html }
}

export default function ChatPage() {
  const { user, logoutUser } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // Determine mode from URL — ?mode=smart activates smart investigator flow
  const isSmartMode = searchParams.get('mode') === 'smart'

  const [messages, setMessages] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [options, setOptions] = useState(null)
  const [showWidget, setShowWidget] = useState(null)
  const [extracted, setExtracted] = useState(null)
  const [done, setDone] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState(null)
  const [similarIncidents, setSimilarIncidents] = useState(null)
  const [suggestedActions, setSuggestedActions] = useState(null)
  const [reportId, setReportId] = useState(null)
  const bottomRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [selectedIncident, setSelectedIncident] = useState(null)

  useEffect(() => {
    const resumeSessionId = searchParams.get('resume')
    const resumeMode = searchParams.get('resumeMode')
    // Reset all state when mode changes
    setMessages([])
    setSessionId(null)
    setOptions(null)
    setShowWidget(null)
    setExtracted(null)
    setDone(false)
    setInput('')
    setSaveMsg(null)
    setSimilarIncidents(null)
    setSuggestedActions(null)
    setReportId(null)
    if (resumeSessionId) {
      initResume(resumeSessionId, resumeMode === 'smart')
    } else {
      initChat()
    }
  }, [isSmartMode]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, similarIncidents])

  const initChat = async () => {
    setLoading(true)
    try {
      const data = isSmartMode ? await startSmartChat() : await startChat()
      setSessionId(data.session_id)
      addMessage(data.response, 'bot')
      if (data.options) setOptions(data.options)
      if (data.show_widget) setShowWidget(data.show_widget)
    } catch (e) {
      addMessage('Failed to connect. Make sure the backend is running.', 'error')
    } finally {
      setLoading(false)
    }
  }

  const initResume = async (resumeSessionId, smartResume = false) => {
    setLoading(true)
    try {
      const data = smartResume
        ? await resumeSmartChat(resumeSessionId)
        : await resumeChat(resumeSessionId)
      setSessionId(data.session_id)
      addMessage(data.response, 'bot')
      if (data.extracted) setExtracted(data.extracted)
      if (data.show_widget) setShowWidget(data.show_widget)
    } catch (e) {
      addMessage('Could not resume session. Starting a new report.', 'error')
      initChat()
    } finally {
      setLoading(false)
    }
  }

  const addMessage = (text, sender) => {
    setMessages(prev => [...prev, { text, sender, id: Date.now() + Math.random() }])
  }

  const addSummaryMessage = (text) => {
    setMessages(prev => [...prev, { text, sender: 'summary', id: Date.now() + Math.random() }])
  }

  const handleSend = async (text, isButton = false) => {
    if (!text.trim() || loading || done) return
    addMessage(text, 'user')
    setInput('')
    setOptions(null)
    setShowWidget(null)
    setLoading(true)

    try {
      let buttonChoice = isButton ? text : null
      // Standard mode button mappings
      if (text === "Yes, that's correct") buttonChoice = 'confirm_incident_type'
      if (text === "That's not right") buttonChoice = 'wrong_incident_type'

      const data = isSmartMode
        ? await sendSmartMessage(sessionId, isButton ? null : text, buttonChoice)
        : await sendMessage(sessionId, isButton ? null : text, buttonChoice)

      if (data.response === '__SUBMIT__' || data.report_id) {
        addMessage(`Report submitted successfully! Report ID: #${data.report_id}`, 'bot')
        setDone(true)
        setExtracted(null)
        setReportId(data.report_id)

        if (data.similar_incidents && data.similar_incidents.length > 0) {
          setSimilarIncidents(data.similar_incidents)
        }
        if (data.suggested_actions && data.suggested_actions.length > 0) {
          setSuggestedActions(data.suggested_actions)
        }
        return
      }

      addMessage(data.response, 'bot')
      if (data.options) setOptions(data.options)
      if (data.show_widget) setShowWidget(data.show_widget)
      if (data.extracted) setExtracted(data.extracted)
      // If summary-buttons are shown, re-render last message as summary card
      if (data.show_widget === 'summary-buttons') {
        setMessages(prev => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last && last.sender === 'bot') {
            updated[updated.length - 1] = { ...last, sender: 'summary' }
          }
          return updated
        })
      }
    } catch (e) {
      addMessage('Something went wrong. Please try again.', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveProgress = async () => {
    if (!sessionId || saving) return
    setSaving(true)
    setSaveMsg(null)
    try {
      isSmartMode ? await saveSmartProgress(sessionId) : await saveProgress(sessionId)
      setSaveMsg('Progress saved')
      setTimeout(() => setSaveMsg(null), 3000)
    } catch (e) {
      setSaveMsg('Failed to save')
      setTimeout(() => setSaveMsg(null), 3000)
    } finally {
      setSaving(false)
    }
  }

  const handleMicStart = async () => {
    if (recording || loading || done) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data)
      }

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        if (blob.size === 0) return

        setTranscribing(true)
        try {
          const formData = new FormData()
          formData.append('file', blob, 'audio.webm')

          const token = localStorage.getItem('token')
          const res = await fetch('http://localhost:8000/transcribe/', {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: formData
          })
          const data = await res.json()
          if (data.text) {
            setInput(prev => prev ? `${prev} ${data.text}` : data.text)
          }
        } catch (e) {
          console.error('Transcription failed:', e)
        } finally {
          setTranscribing(false)
        }
      }

      mediaRecorder.start()
      setRecording(true)
    } catch (e) {
      alert('Microphone access denied. Please allow microphone access in your browser.')
    }
  }

  const handleMicStop = () => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop()
      setRecording(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend(input)
    }
  }

  const startNew = (smart = false) => {
    setMessages([])
    setSessionId(null)
    setOptions(null)
    setShowWidget(null)
    setExtracted(null)
    setDone(false)
    setInput('')
    setSaveMsg(null)
    setSimilarIncidents(null)
    setSuggestedActions(null)
    setReportId(null)
    navigate(smart ? '/chat?mode=smart' : '/chat', { replace: true })
    // Small delay to let URL update before initChat reads searchParams
    setTimeout(() => window.location.reload(), 50)
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
            className={`w-full text-left px-3 py-2 rounded text-sm font-mono transition-colors ${
              !isSmartMode ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            + New Report
          </button>
          <button
            onClick={() => navigate('/chat?mode=smart')}
            className={`w-full text-left px-3 py-2 rounded text-sm font-mono transition-colors ${
              isSmartMode ? 'bg-orange-500/20 text-orange-400 border border-orange-800' : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            ✦ Smart Report
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
          <button
            onClick={logoutUser}
            className="text-gray-500 hover:text-red-400 text-xs font-mono transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-white font-semibold">
                {isSmartMode ? 'Smart Incident Investigation' : 'Incident Report'}
              </h1>
              {isSmartMode && (
                <span className="text-xs font-mono bg-orange-500/20 text-orange-400 border border-orange-800 px-2 py-0.5 rounded">
                  AI Investigator
                </span>
              )}
            </div>
            <p className="text-gray-500 text-xs font-mono">
              {sessionId ? `Session: ${sessionId.slice(0, 8)}...` : 'Starting...'}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {saveMsg && (
              <span className={`text-xs font-mono ${saveMsg === 'Progress saved' ? 'text-green-400' : 'text-red-400'}`}>
                {saveMsg}
              </span>
            )}
            {!done && sessionId && (
              <button
                onClick={handleSaveProgress}
                disabled={saving}
                className="text-gray-500 hover:text-white border border-gray-700 hover:border-gray-500 text-xs font-mono px-3 py-1.5 rounded transition-colors disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Progress'}
              </button>
            )}
            {done && (
              <div className="flex items-center gap-3">
                {reportId && (
                  <button
                    onClick={() => navigate(`/reports/${reportId}`)}
                    className="text-orange-500 hover:text-orange-400 text-xs font-mono border border-orange-800 hover:border-orange-500 px-3 py-1.5 rounded transition-colors"
                  >
                    View Report
                  </button>
                )}
                <button
                  onClick={() => startNew(false)}
                  className="border border-gray-700 hover:border-gray-500 text-gray-300 hover:text-white text-sm font-mono px-4 py-2 rounded transition-colors"
                >
                  New Report
                </button>
                <button
                  onClick={() => startNew(true)}
                  className="bg-orange-500 hover:bg-orange-400 text-white text-sm font-mono px-4 py-2 rounded transition-colors"
                >
                  ✦ Smart Report
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.sender === 'summary' ? (
                <div className="max-w-xl w-full bg-gray-900 border border-orange-800/40 rounded-lg overflow-hidden">
                  <div className="bg-orange-500/10 border-b border-orange-800/40 px-4 py-2">
                    <span className="text-orange-400 text-xs font-mono uppercase tracking-wider">Incident Summary</span>
                  </div>
                  <div
                    className="px-4 py-3 text-sm text-gray-200 leading-relaxed"
                    dangerouslySetInnerHTML={renderMarkdown(msg.text)}
                  />
                </div>
              ) : (
                <div
                  className={`max-w-xl px-4 py-3 rounded-lg text-sm leading-relaxed ${
                    msg.sender === 'user'
                      ? 'bg-orange-500 text-white'
                      : msg.sender === 'error'
                      ? 'bg-red-950 border border-red-800 text-red-400 font-mono'
                      : 'bg-gray-800 text-gray-100'
                  }`}
                  dangerouslySetInnerHTML={msg.sender === 'bot' ? renderMarkdown(msg.text) : undefined}
                >
                  {msg.sender !== 'bot' ? msg.text : undefined}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-gray-800 px-4 py-3 rounded-lg">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}

          {/* Option buttons */}
          {options && !loading && (
            <div className="flex flex-wrap gap-2 justify-start">
              {options.map((opt) => (
                <button
                  key={opt}
                  onClick={() => handleSend(opt, true)}
                  className="bg-gray-800 hover:bg-gray-700 border border-gray-700 hover:border-orange-500 text-white text-sm px-4 py-2 rounded transition-all font-mono"
                >
                  {opt}
                </button>
              ))}
            </div>
          )}

          {/* Confirm buttons */}
          {showWidget === 'confirm-buttons' && !loading && (
            <div className="flex gap-2">
              <button
                onClick={() => handleSend('yes')}
                className="bg-green-700 hover:bg-green-600 text-white text-sm px-6 py-2 rounded font-mono transition-colors"
              >
                Looks correct
              </button>
              <button
                onClick={() => handleSend('no')}
                className="bg-gray-800 hover:bg-gray-700 text-white text-sm px-6 py-2 rounded font-mono transition-colors"
              >
                Make a correction
              </button>
            </div>
          )}

          {/* Summary buttons */}
          {showWidget === 'summary-buttons' && !loading && (
            <div className="flex gap-2">
              <button
                onClick={() => handleSend('yes')}
                className="bg-orange-500 hover:bg-orange-400 text-white text-sm px-6 py-2 rounded font-mono transition-colors"
              >
                Submit Report
              </button>
              <button
                onClick={() => handleSend('no')}
                className="bg-gray-800 hover:bg-gray-700 text-white text-sm px-6 py-2 rounded font-mono transition-colors"
              >
                Make a correction
              </button>
            </div>
          )}

          {/* Similar incidents — shown after submit */}
          {done && similarIncidents && similarIncidents.length > 0 && (
            <div className="mt-4">
              <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-3">
                Similar Past Incidents Found ({similarIncidents.length})
              </div>
              <div className="space-y-3">
                {similarIncidents.map((incident, i) => (
                  <SimilarIncidentCard key={i} incident={incident} onClick={() => setSelectedIncident(incident)} />
                ))}
              </div>
            </div>
          )}

          {/* Suggested corrective actions — shown after submit */}
          {done && suggestedActions && suggestedActions.length > 0 && (
            <div className="mt-4">
              <div className="text-gray-500 text-xs font-mono uppercase tracking-wider mb-2">
                Suggested Corrective Actions
              </div>
              <p className="text-gray-600 text-xs font-mono mb-3">
                Based on similar past incidents. Click to copy.
              </p>
              <div className="flex flex-wrap gap-2">
                {suggestedActions.map((action, i) => (
                  <button
                    key={i}
                    id={`action-chip-${i}`}
                    onClick={() => {
                      navigator.clipboard.writeText(action).then(() => {
                        const el = document.getElementById(`action-chip-${i}`)
                        if (el) {
                          const orig = el.textContent
                          el.textContent = 'Copied!'
                          setTimeout(() => { el.textContent = orig }, 1200)
                        }
                      }).catch(() => {})
                    }}
                    className="bg-gray-800 hover:bg-gray-700 border border-gray-700 hover:border-orange-500 text-gray-300 hover:text-white text-xs font-mono px-3 py-2 rounded-full transition-all text-left"
                  >
                    {action}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Extracted data panel */}
        {extracted && (
          <div className="border-t border-gray-800 px-6 py-3 bg-gray-900">
            <div className="text-gray-500 text-xs font-mono mb-2 uppercase tracking-wider">Collected so far</div>
            <div className="flex flex-wrap gap-x-6 gap-y-1">
              {(() => {
                const incidentType = extracted.basic_info?.incident_type || ''
                // Always show basic_info + the relevant section if known
                const sectionsToShow = ['basic_info']
                if (incidentType === 'Personal Injuries') sectionsToShow.push('injury_data')
                else if (incidentType === 'Near Miss') sectionsToShow.push('near_miss_data')
                else if (incidentType === 'Equipment Damage') sectionsToShow.push('equipment_damage_data')
                else {
                  // incident_type not yet known — show all sections that have data
                  ;['injury_data', 'near_miss_data', 'equipment_damage_data'].forEach(s => {
                    if (extracted[s] && Object.values(extracted[s]).some(v => v)) {
                      sectionsToShow.push(s)
                    }
                  })
                }

                return sectionsToShow.map(section =>
                  extracted[section] && typeof extracted[section] === 'object'
                    ? Object.entries(extracted[section]).map(([k, v]) =>
                        v ? (
                          <div key={`${section}.${k}`} className="text-xs font-mono">
                            <span className="text-gray-600">{k.replace(/_/g, ' ')}: </span>
                            <span className="text-orange-400">{v}</span>
                          </div>
                        ) : null
                      )
                    : null
                )
              })()}
            </div>
          </div>
        )}

        {/* Input */}
        {!done && (
          <div className="border-t border-gray-800 p-4">
            <div className="flex gap-3">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading || transcribing}
                placeholder={
                  transcribing ? 'Transcribing...' :
                  isSmartMode ? 'Describe what happened...' :
                  'Type your message...'
                }
                className="flex-1 bg-gray-900 border border-gray-800 text-white px-4 py-3 rounded focus:outline-none focus:border-orange-500 transition-colors font-mono text-sm disabled:opacity-50"
              />
              <button
                onMouseDown={handleMicStart}
                onMouseUp={handleMicStop}
                onTouchStart={handleMicStart}
                onTouchEnd={handleMicStop}
                disabled={loading || transcribing || done}
                title={recording ? 'Release to transcribe' : 'Hold to speak'}
                className={`px-4 py-3 rounded transition-colors font-mono text-sm disabled:opacity-40 select-none ${
                  recording
                    ? 'bg-red-500 hover:bg-red-400 text-white animate-pulse'
                    : transcribing
                    ? 'bg-gray-700 text-gray-400'
                    : 'bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 hover:text-white'
                }`}
              >
                {recording ? '⏹' : transcribing ? '...' : '🎤'}
              </button>
              <button
                onClick={() => handleSend(input)}
                disabled={loading || !input.trim()}
                className="bg-orange-500 hover:bg-orange-400 disabled:bg-gray-800 disabled:text-gray-600 text-white px-5 py-3 rounded transition-colors font-mono text-sm"
              >
                Send
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Similar incident detail modal */}
      <IncidentDetailModal incident={selectedIncident} onClose={() => setSelectedIncident(null)} />
    </div>
  )
}