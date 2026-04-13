import client from './client'

export const startChat = async () => {
  const res = await client.post('/chat/start')
  return res.data
}

export const sendMessage = async (sessionId, message, buttonChoice = null, currentData = null) => {
  const res = await client.post('/chat/message', {
    session_id: sessionId,
    message,
    button_choice: buttonChoice,
    current_data: currentData,
  })
  return res.data
}

export const saveProgress = async (sessionId) => {
  const res = await client.post('/chat/save-progress', { session_id: sessionId })
  return res.data
}

export const resumeChat = async (sessionId) => {
  const res = await client.post('/chat/resume', { session_id: sessionId })
  return res.data
}

// ── SMART REPORT ─────────────────────────────────────────────────────────────

export const startSmartChat = async () => {
  const res = await client.post('/chat/smart-start')
  return res.data
}

export const sendSmartMessage = async (sessionId, message, buttonChoice = null, currentData = null) => {
  const res = await client.post('/chat/smart-message', {
    session_id: sessionId,
    message,
    button_choice: buttonChoice,
    current_data: currentData,
  })
  return res.data
}

export const saveSmartProgress = async (sessionId) => {
  const res = await client.post('/chat/smart-save-progress', { session_id: sessionId })
  return res.data
}

export const resumeSmartChat = async (sessionId) => {
  const res = await client.post('/chat/smart-resume', { session_id: sessionId })
  return res.data
}