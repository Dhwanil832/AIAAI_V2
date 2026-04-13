import client from './client'

export const uploadHistorical = async (file, incidentType) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('incident_type', incidentType)

  const res = await client.post('/historical/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return res.data
}

export const listHistorical = async ({ incident_type = null, skip = 0, limit = 50 } = {}) => {
  const params = new URLSearchParams()
  params.append('skip', skip)
  params.append('limit', limit)
  if (incident_type) params.append('incident_type', incident_type)

  const res = await client.get(`/historical/?${params.toString()}`)
  return res.data
}

export const getHistoricalStats = async () => {
  const res = await client.get('/historical/stats')
  return res.data
}