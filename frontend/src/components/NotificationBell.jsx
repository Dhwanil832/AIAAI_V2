import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { listNotifications, markRead, markAllRead } from '../api/notifications'

export default function NotificationBell() {
  const navigate = useNavigate()
  const [unreadCount, setUnreadCount] = useState(0)
  const [notifications, setNotifications] = useState([])
  const [open, setOpen] = useState(false)
  const dropdownRef = useRef(null)

  useEffect(() => {
    fetchNotifications()
    // Poll every 30 seconds for new notifications
    const interval = setInterval(fetchNotifications, 30000)
    return () => clearInterval(interval)
  }, [])

  // Close dropdown when clicking outside
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
      // Silently fail — bell is non-critical
    }
  }

  const handleOpen = () => {
    setOpen(prev => !prev)
  }

  const handleMarkAllRead = async () => {
    try {
      await markAllRead()
      setUnreadCount(0)
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
    } catch (e) {}
  }

  const handleClickNotification = async (notif) => {
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

  return (
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
              notifications.map(notif => (
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
                      <p className="text-gray-300 text-xs font-mono leading-relaxed">
                        {notif.message}
                      </p>
                      <p className="text-gray-600 text-xs font-mono mt-1">
                        {formatTime(notif.created_at)}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}