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

// Pipeline Activity
export const getPipelineProgress = () => request('/pipeline/progress')
export const getPipelineLog = (limit) => request('/pipeline/log', { params: { limit } })
export const getCookieStatus = () => request('/pipeline/cookie-status')
export const saveCookies = async (text) => {
  const resp = await fetch('/api/pipeline/save-cookies', {
    method: 'POST',
    headers: { 'X-API-Key': localStorage.getItem('apiKey') || '', 'Content-Type': 'text/plain' },
    body: text,
  })
  if (!resp.ok) throw new Error('Cookie upload failed')
  return resp.json()
}

// Content
export const getContentList = (params) => request('/content', { params })
export const getContentPiece = (id) => request(`/content/${id}`)
export const updateContent = (id, data) => request(`/content/${id}`, { method: 'PUT', body: data })
export const approveContent = (id) => request(`/content/${id}/approve`, { method: 'POST' })
export const scheduleContent = (id, data) => request(`/content/${id}/schedule`, { method: 'POST', body: data })

// Campaigns
export const getCampaigns = () => request('/campaigns')
export const createCampaign = (data) => request('/campaigns', { method: 'POST', body: data })
export const syncCampaigns = () => request('/campaigns/sync', { method: 'POST' })

// Tenants
export const createTenant = (data) => request('/tenants', { method: 'POST', body: data })
export const getSettings = () => request('/settings')
export const updateSettings = (data) => request('/settings', { method: 'PUT', body: data })

// Nextcloud
export const ncBrowse = (path) => request('/nc/browse', { method: 'POST', body: { path } })
export const ncSearch = (query) => request('/nc/search', { method: 'POST', body: { query } })
export const ncSuggest = () => request('/nc/suggest', { method: 'POST' })
