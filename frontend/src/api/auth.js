import client from './client'

export const login = async (username, password) => {
  const res = await client.post('/auth/login', { username, password })
  return res.data
}

export const getMe = async () => {
  const res = await client.get('/auth/me')
  return res.data
}