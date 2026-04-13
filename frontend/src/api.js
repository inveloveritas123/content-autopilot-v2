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
export const getSourceStats = () => request('/sources/stats')
export const searchChannels = (query) => request('/sources/search', { method: 'POST', body: { query } })
export const searchVideos = (query) => request('/sources/youtube/search-videos', { method: 'POST', body: { query } })
export const discoverSources = (topics) => request('/sources/discover', { params: { topics } })
export const createSource = (data) => request('/sources', { method: 'POST', body: data })
export const updateSource = (id, data) => request(`/sources/${id}`, { method: 'PUT', body: data })
export const updateSourceKeywords = (id, keywords) => request(`/sources/${id}`, { method: 'PUT', body: { keywords } })
export const deleteSource = (id) => request(`/sources/${id}`, { method: 'DELETE' })
export const checkSource = (id) => request(`/sources/${id}/check`, { method: 'POST' })
export const importAllVideos = (id) => request(`/sources/${id}/import-all`, { method: 'POST' })
export const analyzeAllSourceItems = (id) => request(`/sources/${id}/analyze-all`, { method: 'POST' })
export const archiveSourceItems = (id) => request(`/sources/${id}/archive-items`, { method: 'POST' })
export const getSourceItems = (id, params) => request(`/sources/${id}/items`, { params })
export const syncTranscripts = () => request('/sources/sync-transcripts', { method: 'POST' })

// Items
export const getItems = (params) => request('/items', { params })
export const getItem = (id) => request(`/items/${id}`)
export const transcribeItem = (id) => request(`/items/${id}/transcribe`, { method: 'POST' })
export const analyzeItem = (id) => request(`/items/${id}/analyze`, { method: 'POST' })
export const generateContent = (id) => request(`/items/${id}/generate`, { method: 'POST' })
export const updateAllViews = () => request('/items/update-views', { method: 'POST' })
export const batchTranscribe = () => request('/items/batch-transcribe', { method: 'POST' })
export const retryTranscribe = (id) => request(`/items/${id}/retry-transcribe`, { method: 'POST' })
export const bulkRetryFailed = () => request('/items/bulk-retry-failed', { method: 'POST' })
export const bulkArchiveFailed = () => request('/items/bulk-archive-failed', { method: 'POST' })

// Ideas (v2 dialogic workflow)
export const getIdeas = (params) => request('/ideas', { params })
export const getIdeasFiltered = (params) => request('/ideas', { params })
export const getIdea = (id) => request(`/ideas/${id}`)
export const generateIdeas = (itemId) => request(`/ideas/generate/${itemId}`, { method: 'POST' })
export const batchGenerateIdeas = () => request('/ideas/batch-generate', { method: 'POST' })
export const refreshIdeasWithProfile = (limit = 20) => request(`/ideas/refresh-with-profile?limit=${limit}`, { method: 'POST' })
export const submitAnswer = (ideaId, data) => request(`/ideas/${ideaId}/answer`, { method: 'POST', body: data })
export const generatePost = (ideaId, data) => request(`/ideas/${ideaId}/generate-post`, { method: 'POST', body: data || {} })
export const updateIdea = (ideaId, data) => request(`/ideas/${ideaId}`, { method: 'PATCH', body: data })
export const bulkArchiveIdeas = (params) => request('/ideas/bulk-archive', { method: 'POST', params })
export const quickGeneratePost = (ideaId) => request(`/ideas/${ideaId}/quick-generate`, { method: 'POST' })
export const bulkQuickGeneratePosts = (ideaIds) => request('/ideas/bulk-quick-generate', { method: 'POST', body: { idea_ids: ideaIds } })
export const createManualIdea = (data) => request('/ideas/create-manual', { method: 'POST', body: data })

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
export const bulkApproveContent = (ids) => request('/content/bulk-approve', { method: 'POST', body: { ids: ids || null } })
export const bulkRejectContent = (ids, sourceId) => request('/content/bulk-reject', { method: 'POST', body: { ids: ids || null }, params: sourceId ? { source_id: sourceId } : {} })
export const bulkPublishContent = (ids) => request('/content/bulk-publish', { method: 'POST', body: { ids } })
export const suggestHashtags = (id) => request(`/content/${id}/hashtags`, { method: 'POST' })
export const repurposeContent = (id) => request(`/content/${id}/repurpose`, { method: 'POST' })
export const getHookLibrary = (angle) => request('/hook-library', { params: angle ? { angle } : {} })

export async function downloadContentExport(status) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  const qs = params.toString()
  const url = `${API_BASE}/content/export${qs ? '?' + qs : ''}`
  const resp = await fetch(url, { headers: { 'X-API-Key': getApiKey() } })
  if (!resp.ok) throw new Error('Export fehlgeschlagen')
  const blob = await resp.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `content_export_${new Date().toISOString().slice(0,10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
  return { downloaded: true }
}
export const getBestPostingTimes = () => request('/posts/best-times')

// Scheduling / Calendar
export const schedulePost = (data) => request('/posts/schedule', { method: 'POST', body: data })
export const autoSchedulePosts = (data) => request('/posts/auto-schedule', { method: 'POST', body: data || {} })
export const getScheduledPosts = (status) => request('/posts/scheduled', { params: status ? { status } : {} })
export const getCalendar = (month) => request('/posts/calendar', { params: { month } })
export const updateScheduledPost = (id, data) => request(`/posts/scheduled/${id}`, { method: 'PATCH', body: data })
export const cancelScheduledPost = (id) => request(`/posts/scheduled/${id}`, { method: 'DELETE' })

// Carousels
export const previewCarousel = (contentPieceId, title) => request('/carousels/preview', { method: 'POST', body: { content_piece_id: contentPieceId, title: title || 'LinkedIn Carousel' } })

export async function generateCarousel(contentPieceId, title = 'LinkedIn Carousel') {
  const resp = await fetch(`${API_BASE}/carousels/generate`, {
    method: 'POST',
    headers: { 'X-API-Key': getApiKey(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ content_piece_id: contentPieceId, title }),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || 'Carousel Error')
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title}.pdf`
  a.click()
  URL.revokeObjectURL(url)
  return { downloaded: true }
}
export const getCarouselTemplates = () => request('/carousels/templates')

// Tenants / Voice
export const getVoiceProfile = () => request('/tenants/me/voice-profile').catch(() => null)
export const updateVoiceProfile = (dimensions) => request('/tenants/me/voice-profile', { method: 'PATCH', body: { dimensions } })

// Pipeline
export const getPipelineProgress = () => request('/pipeline/progress')
export const getPipelineLog = (params) => request('/pipeline/log', { params })
export const getCookieStatus = () => request('/pipeline/cookie-status')
export const triggerAutoPipeline = () => request('/pipeline/auto-trigger', { method: 'POST' })
export const getPipelineStatus = () => request('/pipeline/status')
export const resetBudgetFlag = () => request('/pipeline/reset-budget-flag', { method: 'POST' })
export const queueAllAnalysis = (sourceId) => request('/pipeline/queue-all-analysis', { method: 'POST', params: sourceId ? { source_id: sourceId } : {} })
export const getTranscribedBreakdown = () => request('/pipeline/transcribed-breakdown')
export const resetStuckItems = () => request('/pipeline/reset-stuck', { method: 'POST' })
export const getStuckCount = () => request('/pipeline/stuck-count')

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

// LLM Providers
export const getLLMProviders = () => request('/settings/llm-providers')
export const createLLMProvider = (data) => request('/settings/llm-providers', { method: 'POST', body: data })
export const updateLLMProvider = (id, data) => request(`/settings/llm-providers/${id}`, { method: 'PATCH', body: data })
export const deleteLLMProvider = (id) => request(`/settings/llm-providers/${id}`, { method: 'DELETE' })
export const testLLMProvider = (id) => request(`/settings/llm-providers/${id}/test`, { method: 'POST' })
export const getLLMCostHistory = (days = 7) => request('/settings/llm-cost-history', { params: { days } })
export const benchmarkLLM = (step, item_id) => request('/settings/benchmark', { method: 'POST', body: JSON.stringify({ step, item_id: item_id || undefined }) })
export const getVoiceProfilesList = () => request('/settings/voice-profiles-list')
export const runVoiceCompare = (item_id) => request('/settings/voice-compare', { method: 'POST', body: JSON.stringify({ item_id: item_id || undefined }) })

// Projects
export const getProjects = () => request('/projects')
export const createProject = (data) => request('/projects', { method: 'POST', body: data })
export const deleteProject = (id) => request(`/projects/${id}`, { method: 'DELETE' })

// Nextcloud
export const ncBrowse = (path) => request('/nc/browse', { method: 'POST', body: { path } })
export const ncSuggest = () => request('/nc/suggest', { method: 'POST' })

// Activity
export const getActivity = (params) => request('/pipeline/log', { params })
export const getActivityLog = (params) => request('/pipeline/log', { params })

// Content Pillars
export const updateContentPillar = (id, pillar) => request(`/content/${id}/pillar`, { method: 'PATCH', body: { pillar } })

// Quick-Create AI Post
export const quickCreatePost = (data) => request('/content/quick-create', { method: 'POST', body: data })

// Save Direct Post (written by Claude, no backend LLM)
export const saveDirectPost = (data) => request('/content/save-direct', { method: 'POST', body: data })

// Mark as published
export const markPublished = (id) => request(`/content/${id}/mark-published`, { method: 'POST' })
export const updateContentTags = (id, tags) => request(`/content/${id}/tags`, { method: 'PATCH', body: { tags } })

// Source funnel analytics
export const getSourceFunnel = () => request('/sources/funnel')

// Content Series Builder
export const createContentSeries = (data) => request('/content/create-series', { method: 'POST', body: data })

// URL → Post
export const postFromUrl = (data) => request('/content/post-from-url', { method: 'POST', body: data })

// AI Post Rewriter
export const rewriteContent = (id, mode) => request(`/content/${id}/rewrite`, { method: 'POST', body: { mode } })

// A/B Variant Generator
export const generateVariants = (id) => request(`/content/${id}/variants`, { method: 'POST' })

// Multi-Format Repurposer
export const repurposeFormats = (id) => request(`/content/${id}/repurpose-formats`, { method: 'POST' })

// AI Daily Content Brief
export const getTodayBrief = () => request('/content/today-brief')

// Performance Predictor
export const predictPerformance = (id) => request(`/content/${id}/predict-performance`, { method: 'POST' })

// Ideas Analytics
export const getIdeasStats = () => request('/ideas/stats')
export const getIdeasSourceBreakdown = () => request('/ideas/source-breakdown')

// Quality Analytics
export const getQualitySummary = (days = 30) => request('/quality/summary', { params: { days } })
export const getQualityByModel = (days = 30, step) => request('/quality/by-model', { params: { days, ...(step ? {step} : {}) } })
export const getQualityRecent = (limit = 20, step) => request('/quality/recent', { params: { limit, ...(step ? {step} : {}) } })
export const rateItemQuality = (itemId, step, rating) => request(`/quality/items/${itemId}/rate`, { method: 'POST', params: { step }, body: { rating } })
export const getProductionHeatmap = (days = 90) => request('/quality/production-heatmap', { params: { days } })


// LLM Routing
export const getLlmRouting = () => request('/settings/llm-routing')

// Dialogue Workflow
export const getDialogueItems = (limit = 30, readyOnly = false) =>
  request('/dialogue/items', { params: { limit, ready_only: readyOnly } })
export const getDialogueContext = (itemId) => request(`/dialogue/items/${itemId}/context`)
export const submitDialogueAnswers = (itemId, answers) =>
  request(`/dialogue/items/${itemId}/answers`, { method: 'POST', body: { answers } })
export const generateDialoguePostPrompt = (itemId, format = 'story') =>
  request(`/dialogue/items/${itemId}/generate-post`, { method: 'POST', params: { format, use_claude_direct: true } })
