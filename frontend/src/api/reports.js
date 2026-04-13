import client from './client'

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