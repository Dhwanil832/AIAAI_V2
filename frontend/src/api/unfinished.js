import client from './client'

export const listUnfinished = async () => {
  const res = await client.get('/unfinished/')
  return res.data
}

export const discardUnfinished = async (id) => {
  const res = await client.delete(`/unfinished/${id}`)
  return res.data
}