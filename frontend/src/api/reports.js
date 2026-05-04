import client from './client'

// ── EXISTING FUNCTIONS — UNCHANGED ───────────────────────────────────────────

export const listReports = async ({ skip = 0, limit = 20, incident_type = null, flagged = null, search = null } = {}) => {
  const params = new URLSearchParams()
  params.append('skip', skip)
  params.append('limit', limit)
  if (incident_type) params.append('incident_type', incident_type)
  if (flagged !== null) params.append('flagged', flagged)
  if (search) params.append('search', search)

  const res = await client.get(`/reports/?${params.toString()}`)
  return res.data
}

export const getReport = async (id) => {
  const res = await client.get(`/reports/${id}`)
  return res.data
}

export const toggleFlag = async (id) => {
  const res = await client.patch(`/reports/${id}/flag`)
  return res.data
}

export const editReport = async (id, updates) => {
  const res = await client.patch(`/reports/${id}/edit`, updates)
  return res.data
}

export const deleteReport = async (id) => {
  const res = await client.delete(`/reports/${id}`)
  return res.data
}

// ── WITNESS FUNCTIONS — NEW ───────────────────────────────────────────────────

export const getPendingWitnessRequests = async () => {
  const res = await client.get('/reports/witness-pending')
  return res.data
}

export const getWitnessSubmissions = async () => {
  const res = await client.get('/reports/witness-submissions')
  return res.data
}

export const getWitnessView = async (reportId) => {
  const res = await client.get(`/reports/${reportId}/witness-view`)
  return res.data
}

export const nominateWitness = async (reportId, username) => {
  const res = await client.post(`/reports/${reportId}/nominate-witness`, { username })
  return res.data
}

export const submitWitnessAccount = async (reportId, account) => {
  const res = await client.post(`/reports/${reportId}/witness-account`, { account })
  return res.data
}

export const regenerateSummary = async (reportId) => {
  const res = await client.post(`/reports/${reportId}/regenerate-summary`)
  return res.data
}
export const generateBriefing = async (reportId) => {
  const res = await client.post(`/reports/${reportId}/generate-briefing`)
  return res.data
}
export const exportReports = async ({ format = 'json', date_range = 'all', incident_type = null, location = null, flagged = null } = {}) => {
  const params = new URLSearchParams()
  params.append('format', format)
  params.append('date_range', date_range)
  if (incident_type) params.append('incident_type', incident_type)
  if (location) params.append('location', location)
  if (flagged !== null) params.append('flagged', flagged)

  const res = await client.get(`/reports/export?${params.toString()}`, {
    responseType: 'blob'
  })

  // Trigger download
  const contentDisposition = res.headers['content-disposition'] || ''
  const filenameMatch = contentDisposition.match(/filename=(.+)/)
  const filename = filenameMatch ? filenameMatch[1] : `incident_reports.${format}`

  const url = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}