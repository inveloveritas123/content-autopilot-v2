const API_BASE = '/api'

function getApiKey() {
  return localStorage.getItem('apiKey') || ''
}

export function setApiKey(key) {
  localStorage.setItem('apiKey', key)
}

async function request(path, options = {}) {
  const { method = 'GET', body, params } = options
  let url = `${API_BASE}${path}`
  if (params) {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') searchParams.set(k, v)
    })
    const qs = searchParams.toString()
    if (qs) url += `?${qs}`
  }

  const headers = { 'X-API-Key': getApiKey() }
  if (body) headers['Content-Type'] = 'application/json'

  const resp = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || 'API Error')
  }
  return resp.json()
}

// Dashboard
export const getDashboard = () => request('/dashboard')

// Sources
export const getSources = () => request('/sources')
export const searchChannels = (query) => request('/sources/search', { method: 'POST', body: { query } })
export const createSource = (data) => request('/sources', { method: 'POST', body: data })
export const updateSource = (id, data) => request(`/sources/${id}`, { method: 'PUT', body: data })
export const deleteSource = (id) => request(`/sources/${id}`, { method: 'DELETE' })
export const checkSource = (id) => request(`/sources/${id}/check`, { method: 'POST' })
export const importAllVideos = (id) => request(`/sources/${id}/import-all`, { method: 'POST' })
export const syncTranscripts = () => request('/sources/sync-transcripts', { method: 'POST' })

// Items
export const getItems = (params) => request('/items', { params })
export const getItem = (id) => request(`/items/${id}`)
export const transcribeItem = (id) => request(`/items/${id}/transcribe`, { method: 'POST' })
export const analyzeItem = (id) => request(`/items/${id}/analyze`, { method: 'POST' })
export const generateContent = (id) => request(`/items/${id}/generate`, { method: 'POST' })
export const updateAllViews = () => request('/items/update-views', { method: 'POST' })
export const batchTranscribe = () => request('/items/batch-transcribe', { method: 'POST' })

// Ideas (v2 dialogic workflow)
export const getIdeas = (params) => request('/ideas', { params })
export const getIdea = (id) => request(`/ideas/${id}`)
export const generateIdeas = (itemId) => request(`/ideas/generate/${itemId}`, { method: 'POST' })
export const submitAnswer = (ideaId, data) => request(`/ideas/${ideaId}/answer`, { method: 'POST', body: data })
export const generatePost = (ideaId, data) => request(`/ideas/${ideaId}/generate-post`, { method: 'POST', body: data || {} })
export const updateIdea = (ideaId, data) => request(`/ideas/${ideaId}`, { method: 'PATCH', body: data })

// Feedback
export const submitEditDiff = (data) => request('/feedback/edit-diff', { method: 'POST', body: data })
export const submitPerformance = (data) => request('/feedback/performance', { method: 'POST', body: data })
export const submitIdeaSelection = (data) => request('/feedback/idea-selection', { method: 'POST', body: data })
export const getFeedbackStats = () => request('/feedback/stats')

// Content
export const getContentList = (params) => request('/content', { params })
export const getContentPiece = (id) => request(`/content/${id}`)
export const updateContent = (id, data) => request(`/content/${id}`, { method: 'PUT', body: data })
export const approveContent = (id) => request(`/content/${id}/approve`, { method: 'POST' })

// Tenants / Voice
export const getVoiceProfile = () => request('/tenants/me/voice-profile').catch(() => null)
export const updateVoiceProfile = (dimensions) => request('/tenants/me/voice-profile', { method: 'PATCH', body: { dimensions } })

// Pipeline
export const getPipelineProgress = () => request('/pipeline/progress')
export const getPipelineLog = (params) => request('/pipeline/log', { params })
export const getCookieStatus = () => request('/pipeline/cookie-status')

// Cookies
export async function saveCookies(cookieText) {
  const resp = await fetch(`${API_BASE}/pipeline/save-cookies`, {
    method: 'POST',
    headers: { 'X-API-Key': getApiKey(), 'Content-Type': 'text/plain' },
    body: cookieText,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || 'API Error')
  }
  return resp.json()
}

// Settings
export const getSettings = () => request('/settings')
export const updateSettings = (data) => request('/settings', { method: 'PUT', body: data })

// Nextcloud
export const ncBrowse = (path) => request('/nc/browse', { method: 'POST', body: { path } })
export const ncSuggest = () => request('/nc/suggest', { method: 'POST' })

// Activity
export const getActivity = (params) => request('/pipeline/log', { params })
