import client from './client'

export const listNotifications = async () => {
  const res = await client.get('/notifications/')
  return res.data
}

export const markRead = async (id) => {
  const res = await client.patch(`/notifications/${id}/read`)
  return res.data
}

export const markAllRead = async () => {
  const res = await client.patch('/notifications/read-all')
  return res.data
}