import { useState, useEffect, useRef } from 'react'
import { uploadPostSubmission, replyToThread, getReporterThread, fileToBase64 } from '../api/vision'

export default function VisionThreadModal({ reportId, threadId, onClose }) {
  const [conversation, setConversation] = useState([])
  const [status, setStatus]             = useState('open')
  const [hasImage, setHasImage]         = useState(false)
  const [uploading, setUploading]       = useState(false)
  const [input, setInput]               = useState('')
  const [sending, setSending]           = useState(false)
  const [resolved, setResolved]         = useState(false)
  const [error, setError]               = useState(null)
  const [loading, setLoading]           = useState(true)
  const fileInputRef                    = useRef(null)
  const bottomRef                       = useRef(null)

  // Load existing thread state
  useEffect(() => {
    if (!reportId) return
    loadThread()
  }, [reportId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation])

  async function loadThread() {
    setLoading(true)
    try {
      const data = await getReporterThread(reportId)
      setConversation(data.conversation || [])
      setStatus(data.status)
      setHasImage(data.has_images)
      setResolved(data.status === 'resolved')
    } catch (e) {
      // Thread may not exist yet — that's fine, reporter hasn't uploaded yet
      setConversation([])
    } finally {
      setLoading(false)
    }
  }

  async function handleFileSelect(e) {
    const file = e.target.files?.[0]
    if (!file || !threadId) return

    setUploading(true)
    setError(null)

    try {
      const imageB64  = await fileToBase64(file)
      const imageType = file.type || 'image/jpeg'

      const result = await uploadPostSubmission(threadId, imageB64, imageType, file.name)

      setHasImage(true)
      setConversation(prev => [
        ...prev,
        { role: 'reporter', content: '📷 Photo uploaded', timestamp: new Date().toISOString() },
        { role: 'agent',    content: result.message,      timestamp: new Date().toISOString() }
      ])

      if (result.resolved) {
        setResolved(true)
        setStatus('resolved')
      }
    } catch (e) {
      setError('Something went wrong uploading the photo. Please try again.')
    } finally {
      setUploading(false)
      // Reset file input so same file can be re-selected if needed
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function handleSend() {
    const msg = input.trim()
    if (!msg || sending || !threadId) return

    setSending(true)
    setInput('')
    setError(null)

    setConversation(prev => [
      ...prev,
      { role: 'reporter', content: msg, timestamp: new Date().toISOString() }
    ])

    try {
      const result = await replyToThread(threadId, msg)

      setConversation(prev => [
        ...prev,
        { role: 'agent', content: result.message, timestamp: new Date().toISOString() }
      ])

      if (result.resolved) {
        setResolved(true)
        setStatus('resolved')
      }
    } catch (e) {
      setError('Could not send your message. Please try again.')
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-end sm:items-center justify-center z-50 p-0 sm:p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-t-2xl sm:rounded-xl w-full sm:max-w-md flex flex-col"
        style={{ maxHeight: '85vh' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
          <div>
            <div className="text-white text-sm font-semibold">Follow-up on Report #{reportId}</div>
            <div className="text-gray-500 text-xs font-mono mt-0.5">
              {resolved ? 'Resolved — thanks for your help' : 'Safety team follow-up'}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white text-xs font-mono transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Conversation */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {loading && (
            <div className="text-gray-600 text-xs font-mono text-center py-6">Loading...</div>
          )}

          {!loading && conversation.length === 0 && !hasImage && (
            <div className="text-gray-500 text-xs font-mono text-center py-4 leading-relaxed">
              The safety team has requested a photo to help with the investigation.
              <br />Tap below to attach one.
            </div>
          )}

          {conversation.map((turn, i) => {
            const isAgent = turn.role === 'agent'
            return (
              <div
                key={i}
                className={`flex ${isAgent ? 'justify-start' : 'justify-end'}`}
              >
                <div
                  className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm font-mono leading-relaxed ${
                    isAgent
                      ? 'bg-gray-800 text-gray-200 rounded-tl-sm'
                      : 'bg-orange-500 text-white rounded-tr-sm'
                  }`}
                >
                  {turn.content}
                </div>
              </div>
            )
          })}

          {(uploading || sending) && (
            <div className="flex justify-start">
              <div className="bg-gray-800 text-gray-500 text-sm font-mono px-4 py-2.5 rounded-2xl rounded-tl-sm">
                <span className="animate-pulse">···</span>
              </div>
            </div>
          )}

          {resolved && (
            <div className="text-center py-2">
              <span className="text-green-500 text-xs font-mono">✓ Conversation complete</span>
            </div>
          )}

          {error && (
            <div className="text-red-400 text-xs font-mono text-center py-1">{error}</div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Actions */}
        {!resolved && !loading && (
          <div className="border-t border-gray-800 p-4 space-y-3 shrink-0">

            {/* Image upload — shown until first image is sent */}
            {!hasImage && (
              <>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  capture="environment"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="w-full bg-gray-800 hover:bg-gray-700 border border-gray-700 hover:border-orange-500 text-gray-300 hover:text-white text-sm font-mono py-3 rounded-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {uploading ? (
                    <><span className="animate-pulse">Uploading...</span></>
                  ) : (
                    <><span>📷</span><span>Attach a photo</span></>
                  )}
                </button>
              </>
            )}

            {/* Text reply — shown after image is uploaded */}
            {hasImage && (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={sending}
                  placeholder="Type your reply..."
                  className="flex-1 bg-gray-900 border border-gray-800 text-white px-4 py-2.5 rounded-lg focus:outline-none focus:border-orange-500 transition-colors font-mono text-sm disabled:opacity-50"
                />
                <button
                  onClick={handleSend}
                  disabled={sending || !input.trim()}
                  className="bg-orange-500 hover:bg-orange-400 disabled:bg-gray-800 disabled:text-gray-600 text-white px-4 py-2.5 rounded-lg transition-colors font-mono text-sm"
                >
                  Send
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}