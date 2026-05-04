import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { listNotifications, markRead, markAllRead } from '../api/notifications'
import VisionThreadModal from './VisionThreadModal'

export default function NotificationBell({ onWitnessClick }) {
  const navigate = useNavigate()
  const [unreadCount, setUnreadCount]       = useState(0)
  const [notifications, setNotifications]   = useState([])
  const [open, setOpen]                     = useState(false)
  const dropdownRef                         = useRef(null)

  // Vision thread modal state — managed here so no parent wiring needed
  const [visionModal, setVisionModal]       = useState(null) // { reportId, threadId }

  useEffect(() => {
    fetchNotifications()
    const interval = setInterval(fetchNotifications, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const fetchNotifications = async () => {
    try {
      const data = await listNotifications()
      setUnreadCount(data.unread_count)
      setNotifications(data.notifications)
    } catch (e) {
      // Non-critical — fail silently
    }
  }

  const handleOpen = () => setOpen(prev => !prev)

  const handleMarkAllRead = async () => {
    try {
      await markAllRead()
      setUnreadCount(0)
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
    } catch (e) {}
  }

  const handleClickNotification = async (notif) => {
    // Mark as read first
    if (!notif.is_read) {
      try {
        await markRead(notif.id)
        setNotifications(prev =>
          prev.map(n => n.id === notif.id ? { ...n, is_read: true } : n)
        )
        setUnreadCount(prev => Math.max(0, prev - 1))
      } catch (e) {}
    }

    setOpen(false)

    // Witness notifications — open witness modal on dashboard
    if (notif.notification_type === 'witness' && notif.report_id) {
      if (onWitnessClick) {
        onWitnessClick(notif.report_id)
      } else {
        navigate('/dashboard')
      }
      return
    }

    // Vision image request — open VisionThreadModal directly
    if (notif.notification_type === 'vision_image_request') {
      let threadId = null
      let reportId = notif.report_id || null

      // Parse thread_id from metadata JSON
      if (notif.metadata) {
        try {
          const meta = typeof notif.metadata === 'string'
            ? JSON.parse(notif.metadata)
            : notif.metadata
          threadId = meta.thread_id || null
          reportId = meta.report_id || reportId
        } catch (e) {}
      }

      if (reportId && threadId) {
        setVisionModal({ reportId, threadId })
      } else if (reportId) {
        // Fallback — navigate to report page if thread_id not in metadata
        navigate(`/reports/${reportId}`)
      }
      return
    }

    // Default — navigate to report page
    if (notif.report_id) {
      navigate(`/reports/${notif.report_id}`)
    }
  }

  const formatTime = (iso) => {
    if (!iso) return ''
    const date = new Date(iso)
    const now = new Date()
    const diffMs = now - date
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffMins < 1) return 'just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    return `${diffDays}d ago`
  }

  const getTypeLabel = (notif) => {
    if (notif.notification_type === 'witness') return 'Witness Request'
    if (notif.notification_type === 'vision_image_request') return 'Photo Requested'
    if (notif.notification_type === 'secondary_hazard_confirmed') return 'Hazard Confirmed'
    return null
  }

  const getTypeLabelColor = (notif) => {
    if (notif.notification_type === 'witness') return 'text-yellow-600'
    if (notif.notification_type === 'vision_image_request') return 'text-blue-400'
    if (notif.notification_type === 'secondary_hazard_confirmed') return 'text-red-400'
    return 'text-gray-500'
  }

  return (
    <>
      <div className="relative mb-3" ref={dropdownRef}>
        <button
          onClick={handleOpen}
          className="relative w-full flex items-center gap-2 text-gray-500 hover:text-white text-xs font-mono transition-colors py-1"
        >
          <span>🔔</span>
          <span>Notifications</span>
          {unreadCount > 0 && (
            <span className="ml-auto bg-orange-500 text-white text-xs font-mono rounded-full w-5 h-5 flex items-center justify-center shrink-0">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>

        {open && (
          <div className="absolute bottom-full left-0 mb-2 w-80 bg-gray-900 border border-gray-700 rounded-lg shadow-xl z-50">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
              <span className="text-white text-xs font-mono font-semibold">Notifications</span>
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="text-gray-500 hover:text-orange-400 text-xs font-mono transition-colors"
                >
                  Mark all read
                </button>
              )}
            </div>

            {/* List */}
            <div className="max-h-72 overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="px-4 py-6 text-center text-gray-600 text-xs font-mono">
                  No notifications
                </div>
              ) : (
                notifications.map(notif => {
                  const typeLabel = getTypeLabel(notif)
                  return (
                    <div
                      key={notif.id}
                      onClick={() => handleClickNotification(notif)}
                      className={`px-4 py-3 border-b border-gray-800 last:border-0 cursor-pointer hover:bg-gray-800 transition-colors ${
                        !notif.is_read ? 'bg-gray-800/50' : ''
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        {!notif.is_read && (
                          <div className="w-1.5 h-1.5 bg-orange-500 rounded-full mt-1.5 shrink-0" />
                        )}
                        <div className={!notif.is_read ? '' : 'ml-3.5'}>
                          {typeLabel && (
                            <div className={`text-xs font-mono mb-0.5 ${getTypeLabelColor(notif)}`}>
                              {typeLabel}
                            </div>
                          )}
                          <p className="text-gray-300 text-xs font-mono leading-relaxed">
                            {notif.message}
                          </p>
                          <p className="text-gray-600 text-xs font-mono mt-1">
                            {formatTime(notif.created_at)}
                          </p>
                        </div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        )}
      </div>

      {/* Vision thread modal — mounts when reporter clicks a vision notification */}
      {visionModal && (
        <VisionThreadModal
          reportId={visionModal.reportId}
          threadId={visionModal.threadId}
          onClose={() => setVisionModal(null)}
        />
      )}
    </>
  )
}