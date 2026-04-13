import client from './client'

export const listUsers = async () => {
  const res = await client.get('/users/')
  return res.data
}

export const createUser = async (userData) => {
  const res = await client.post('/users/', userData)
  return res.data
}

export const updateUser = async (userId, updates) => {
  const res = await client.patch(`/users/${userId}`, updates)
  return res.data
}

export const resetPassword = async (userId, newPassword) => {
  const res = await client.post(`/users/${userId}/reset-password`, { new_password: newPassword })
  return res.data
}

export const deleteUser = async (userId) => {
  const res = await client.delete(`/users/${userId}`)
  return res.data
}