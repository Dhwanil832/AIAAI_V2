import client from './client'

// ── Mid-intake image upload ───────────────────────────────────────────────────

export async function uploadMidIntake(sessionId, imageB64, imageType, filename = 'image.jpg') {
  const res = await client.post('/vision/upload-mid-intake', {
    session_id: sessionId,
    image_b64: imageB64,
    image_type: imageType,
    filename
  })
  return res.data
}

// ── Post-submission image upload (reporter uploads via notification) ───────────

export async function uploadPostSubmission(threadId, imageB64, imageType, filename = 'image.jpg') {
  const res = await client.post(`/vision/upload-post-submission/${threadId}`, {
    image_b64: imageB64,
    image_type: imageType,
    filename
  })
  return res.data
}

// ── Reporter reply in vision thread ──────────────────────────────────────────

export async function replyToThread(threadId, message) {
  const res = await client.post(`/vision/reply/${threadId}`, { message })
  return res.data
}

// ── Reporter view — conversation only ────────────────────────────────────────

export async function getReporterThread(reportId) {
  const res = await client.get(`/vision/thread/reporter/${reportId}`)
  return res.data
}

// ── Admin view — full thread with observations, amendments, flags ─────────────

export async function getAdminThread(reportId) {
  const res = await client.get(`/vision/thread/admin/${reportId}`)
  return res.data
}

// ── Helper: file → base64 ─────────────────────────────────────────────────────

export function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      // Strip the data URI prefix — backend expects raw base64
      const base64 = reader.result.split(',')[1]
      resolve(base64)
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}