const API_BASE = '/api'

function getApiKey() {
  return localStorage.getItem('apiKey') || ''
}

export function setApiKey(key) {
  localStorage.setItem('apiKey', key)
}

async function request(path, options = {}) {
  const { method = 'GET', body, params, headers: extraHeaders } = options
  let url = `${API_BASE}${path}`
  if (params) {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') searchParams.set(k, v)
    })
    const qs = searchParams.toString()
    if (qs) url += `?${qs}`
  }

  const headers = { 'X-API-Key': getApiKey(), ...extraHeaders }
  if (body) headers['Content-Type'] = 'application/json'

  const resp = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    // detail kann ein String ODER ein Objekt/Array sein (z.B. 422 mit schema_errors).
    let msg = err.detail
    if (typeof msg !== 'string') {
      msg = (err.detail && (err.detail.message || err.detail.error)) || JSON.stringify(err.detail)
    }
    const e = new Error(msg || 'API Error')
    e.status = resp.status
    e.detail = err.detail
    throw e
  }
  return resp.json()
}

// --- Pipeline-Modell-Hoheit (offizieller Default vs. Test-Override pro Phase) ---
export async function getPipelineModels() {
  return request('/settings/pipeline-models')
}

export async function setPipelineModelOverride(phase, modelId) {
  return request('/settings/pipeline-models', {
    method: 'PATCH',
    body: { phase, model_id: modelId || null },
  })
}

// Dashboard
export const getDashboard = () => request('/dashboard')

// Sources
export const getSources = () => request('/sources')
export const getSourceStats = () => request('/sources/stats')
export const searchChannels = (query) =>
  request('/sources/search', { method: 'POST', body: { query } })
export const searchVideos = (query) =>
  request('/sources/youtube/search-videos', { method: 'POST', body: { query } })
export const discoverSources = (topics) => request('/sources/discover', { params: { topics } })
export const createSource = (data) => request('/sources', { method: 'POST', body: data })
export const updateSource = (id, data) => request(`/sources/${id}`, { method: 'PUT', body: data })
export const updateSourceKeywords = (id, keywords) =>
  request(`/sources/${id}`, { method: 'PUT', body: { keywords } })
export const deleteSource = (id) => request(`/sources/${id}`, { method: 'DELETE' })
export const checkSource = (id) => request(`/sources/${id}/check`, { method: 'POST' })
export const importAllVideos = (id) => request(`/sources/${id}/import-all`, { method: 'POST' })
export const analyzeAllSourceItems = (id) =>
  request(`/sources/${id}/analyze-all`, { method: 'POST' })
export const archiveSourceItems = (id) =>
  request(`/sources/${id}/archive-items`, { method: 'POST' })
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
export const refreshIdeasWithProfile = (limit = 20) =>
  request(`/ideas/refresh-with-profile?limit=${limit}`, { method: 'POST' })
export const submitAnswer = (ideaId, data) =>
  request(`/ideas/${ideaId}/answer`, { method: 'POST', body: data })
export const generatePost = (ideaId, data) =>
  request(`/ideas/${ideaId}/generate-post`, { method: 'POST', body: data || {} })
export const updateIdea = (ideaId, data) =>
  request(`/ideas/${ideaId}`, { method: 'PATCH', body: data })
export const bulkArchiveIdeas = (params) =>
  request('/ideas/bulk-archive', { method: 'POST', params })
export const quickGeneratePost = (ideaId) =>
  request(`/ideas/${ideaId}/quick-generate`, { method: 'POST' })
export const bulkQuickGeneratePosts = (ideaIds) =>
  request('/ideas/bulk-quick-generate', { method: 'POST', body: { idea_ids: ideaIds } })
export const createManualIdea = (data) =>
  request('/ideas/create-manual', { method: 'POST', body: data })

// Feedback
export const submitEditDiff = (data) =>
  request('/feedback/edit-diff', { method: 'POST', body: data })
export const submitPerformance = (data) =>
  request('/feedback/performance', { method: 'POST', body: data })
export const submitIdeaSelection = (data) =>
  request('/feedback/idea-selection', { method: 'POST', body: data })
export const getFeedbackStats = () => request('/feedback/stats')

// Content
export const getContentList = (params) => request('/content', { params })
export const getContentPiece = (id) => request(`/content/${id}`)
export const updateContent = (id, data) => request(`/content/${id}`, { method: 'PUT', body: data })
export const approveContent = (id) => request(`/content/${id}/approve`, { method: 'POST' })
export const bulkApproveContent = (ids) =>
  request('/content/bulk-approve', { method: 'POST', body: { ids: ids || null } })
export const bulkRejectContent = (ids, sourceId) =>
  request('/content/bulk-reject', {
    method: 'POST',
    body: { ids: ids || null },
    params: sourceId ? { source_id: sourceId } : {},
  })
export const bulkPublishContent = (ids) =>
  request('/content/bulk-publish', { method: 'POST', body: { ids } })
export const suggestHashtags = (id) => request(`/content/${id}/hashtags`, { method: 'POST' })
export const repurposeContent = (id) => request(`/content/${id}/repurpose`, { method: 'POST' })
export const getHookLibrary = (angle) =>
  request('/hook-library', { params: angle ? { angle } : {} })

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
  a.download = `content_export_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
  return { downloaded: true }
}
export const getBestPostingTimes = () => request('/posts/best-times')

// Scheduling / Calendar
export const schedulePost = (data) => request('/posts/schedule', { method: 'POST', body: data })
export const autoSchedulePosts = (data) =>
  request('/posts/auto-schedule', { method: 'POST', body: data || {} })
export const getScheduledPosts = (status) =>
  request('/posts/scheduled', { params: status ? { status } : {} })
export const getCalendar = (month) => request('/posts/calendar', { params: { month } })
export const updateScheduledPost = (id, data) =>
  request(`/posts/scheduled/${id}`, { method: 'PATCH', body: data })
export const cancelScheduledPost = (id) => request(`/posts/scheduled/${id}`, { method: 'DELETE' })

// Carousels
export const previewCarousel = (contentPieceId, title) =>
  request('/carousels/preview', {
    method: 'POST',
    body: { content_piece_id: contentPieceId, title: title || 'LinkedIn Carousel' },
  })

export async function generateCarousel(
  contentPieceId,
  title = 'LinkedIn Carousel',
  customSlides = null
) {
  const body = customSlides
    ? { slides: customSlides, title }
    : { content_piece_id: contentPieceId, title }
  const resp = await fetch(`${API_BASE}/carousels/generate`, {
    method: 'POST',
    headers: { 'X-API-Key': getApiKey(), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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
export const updateVoiceProfile = (dimensions) =>
  request('/tenants/me/voice-profile', { method: 'PATCH', body: { dimensions } })

// Automation Kill-Switch (Issue #89)
export const getAutomationStatus = () => request('/tenants/me/automation-status')
export const pauseAutomation = () => request('/tenants/me/pause', { method: 'POST' })
export const resumeAutomation = () => request('/tenants/me/resume', { method: 'POST' })

// UI-Modus: MVP vs Features (Issue #90)
// GET → { mode: "mvp" | "features" }
// PUT → { mode } → { mode }
export const getUiMode = () => request('/tenants/me/ui-mode')
export const setUiMode = (mode) =>
  request('/tenants/me/ui-mode', { method: 'PUT', body: { mode } })

export async function downloadTenantDataExport(format = 'zip') {
  const resp = await fetch(
    `${API_BASE}/tenants/me/data-export?format=${encodeURIComponent(format)}`,
    {
      headers: { 'X-API-Key': getApiKey() },
    }
  )
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || 'Export fehlgeschlagen')
  }
  const blob = await resp.blob()
  const dateStr = new Date().toISOString().slice(0, 10)
  const extMap = { zip: '.zip', excel: '.xlsx', csv: '-csv.zip', all: '-all.zip' }
  const ext = extMap[format] ?? '.zip'
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `cap-export-${dateStr}${ext}`
  a.click()
  URL.revokeObjectURL(a.href)
  return { downloaded: true }
}

export const importTenantData = async (file, dryRun = true, merge = true) => {
  const fd = new FormData()
  fd.append('file', file)
  const resp = await fetch(
    `${API_BASE}/tenants/me/data-import?dry_run=${dryRun}&confirm=${!dryRun}&merge=${merge}`,
    { method: 'POST', headers: { 'X-API-Key': getApiKey() }, body: fd }
  )
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || 'Import fehlgeschlagen')
  }
  return resp.json()
}

// Pipeline
export const getPipelineProgress = () => request('/pipeline/progress')
export const getPipelineLog = (params) => request('/pipeline/log', { params })
export const getCookieStatus = () => request('/pipeline/cookie-status')
export const triggerAutoPipeline = () => request('/pipeline/auto-trigger', { method: 'POST' })
export const getPipelineStatus = () => request('/pipeline/status')
export const resetBudgetFlag = () => request('/pipeline/reset-budget-flag', { method: 'POST' })
export const queueAllAnalysis = (sourceId) =>
  request('/pipeline/queue-all-analysis', {
    method: 'POST',
    params: sourceId ? { source_id: sourceId } : {},
  })
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
export const createLLMProvider = (data) =>
  request('/settings/llm-providers', { method: 'POST', body: data })
export const updateLLMProvider = (id, data) =>
  request(`/settings/llm-providers/${id}`, { method: 'PATCH', body: data })
export const deleteLLMProvider = (id) =>
  request(`/settings/llm-providers/${id}`, { method: 'DELETE' })
export const testLLMProvider = (id) =>
  request(`/settings/llm-providers/${id}/test`, { method: 'POST' })
export const getLLMCostHistory = (days = 7) =>
  request('/settings/llm-cost-history', { params: { days } })
export const benchmarkLLM = (step, item_id) =>
  request('/settings/benchmark', {
    method: 'POST',
    body: JSON.stringify({ step, item_id: item_id || undefined }),
  })
export const resetLLMProviderCost = (id) =>
  request(`/settings/llm-providers/${id}/reset-cost`, { method: 'POST' })
export const getVoiceProfilesList = () => request('/settings/voice-profiles-list')
export const runVoiceCompare = (item_id) =>
  request('/settings/voice-compare', {
    method: 'POST',
    body: JSON.stringify({ item_id: item_id || undefined }),
  })

export const listProviderModels = (api_key, base_url) =>
  request('/settings/llm-providers/list-models', { method: 'POST', body: { api_key, base_url } })
export const probeTestProvider = (api_key, base_url, model) =>
  request('/settings/llm-providers/probe-test', {
    method: 'POST',
    body: { api_key, base_url, model },
  })

// Projects
export const getProjects = () => request('/projects')
export const createProject = (data) => request('/projects', { method: 'POST', body: data })
export const updateProject = (id, data) =>
  request(`/projects/${id}`, { method: 'PATCH', body: data })
export const deleteProject = (id) => request(`/projects/${id}`, { method: 'DELETE' })

// Nextcloud
export const ncBrowse = (path) => request('/nc/browse', { method: 'POST', body: { path } })
export const ncSuggest = () => request('/nc/suggest', { method: 'POST' })

// Activity
export const getActivity = (params) => request('/pipeline/log', { params })
export const getActivityLog = (params) => request('/pipeline/log', { params })

// Content Pillars
export const updateContentPillar = (id, pillar) =>
  request(`/content/${id}/pillar`, { method: 'PATCH', body: { pillar } })

// Quick-Create AI Post
export const quickCreatePost = (data) =>
  request('/content/quick-create', { method: 'POST', body: data })

// Save Direct Post (written by Claude, no backend LLM)
export const saveDirectPost = (data) =>
  request('/content/save-direct', { method: 'POST', body: data })

// Mark as published
export const markPublished = (id) => request(`/content/${id}/mark-published`, { method: 'POST' })
export const updateContentTags = (id, tags) =>
  request(`/content/${id}/tags`, { method: 'PATCH', body: { tags } })

// Source funnel analytics
export const getSourceFunnel = () => request('/sources/funnel')

// Content Series Builder
export const createContentSeries = (data) =>
  request('/content/create-series', { method: 'POST', body: data })

// URL → Post
export const postFromUrl = (data) =>
  request('/content/post-from-url', { method: 'POST', body: data })

// AI Post Rewriter
export const rewriteContent = (id, mode) =>
  request(`/content/${id}/rewrite`, { method: 'POST', body: { mode } })

// A/B Variant Generator
export const generateVariants = (id) => request(`/content/${id}/variants`, { method: 'POST' })

// Multi-Format Repurposer
export const repurposeFormats = (id) =>
  request(`/content/${id}/repurpose-formats`, { method: 'POST' })

// AI Daily Content Brief
export const getTodayBrief = () => request('/content/today-brief')

// Performance Predictor
export const predictPerformance = (id) =>
  request(`/content/${id}/predict-performance`, { method: 'POST' })

// Ideas Analytics
export const getIdeasStats = () => request('/ideas/stats')
export const getIdeasSourceBreakdown = () => request('/ideas/source-breakdown')

// Quality Analytics
export const getQualitySummary = (days = 30) => request('/quality/summary', { params: { days } })
export const getQualityByModel = (days = 30, step) =>
  request('/quality/by-model', { params: { days, ...(step ? { step } : {}) } })
export const getQualityRecent = (limit = 20, step) =>
  request('/quality/recent', { params: { limit, ...(step ? { step } : {}) } })
export const rateItemQuality = (itemId, step, rating) =>
  request(`/quality/items/${itemId}/rate`, { method: 'POST', params: { step }, body: { rating } })
export const getProductionHeatmap = (days = 90) =>
  request('/quality/production-heatmap', { params: { days } })

// LLM Routing
export const getLlmRouting = () => request('/settings/llm-routing')

// Dialogue Workflow
export const getDialogueItems = (limit = 30, readyOnly = false) =>
  request('/dialogue/items', { params: { limit, ready_only: readyOnly } })
export const getDialogueContext = (itemId) => request(`/dialogue/items/${itemId}/context`)
export const submitDialogueAnswers = (itemId, answers) =>
  request(`/dialogue/items/${itemId}/answers`, { method: 'POST', body: { answers } })
export const generateDialoguePostPrompt = (itemId, format = 'story') =>
  request(`/dialogue/items/${itemId}/generate-post`, {
    method: 'POST',
    params: { format, use_claude_direct: true },
  })

// Brand Voice API (#59)
export const getBrandVoiceStatus = (tenantId, projectId) =>
  request(`/brand-voice/${tenantId}`, { params: projectId ? { project_id: projectId } : undefined })
export async function uploadBrandVoiceFile(formData) {
  const resp = await fetch(`${API_BASE}/brand-voice/upload`, {
    method: 'POST',
    headers: { 'X-API-Key': getApiKey() },
    body: formData,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || 'Upload fehlgeschlagen')
  }
  return resp.json()
}
export const importBrandVoiceFromNC = (tenantId, path, sourceType) =>
  request('/brand-voice/import-source', {
    method: 'POST',
    body: { tenant_id: tenantId, source_path: path, source_type: sourceType },
  })
export const getBrandVoicePipelineStatus = (runId) => request(`/brand-voice/pipeline/${runId}`)

// Brand Voice Wizard (#70)
export async function getWizardQuestions() {
  const res = await request('/brand-voice/wizard/questions')
  return res.phases
}
export const startWizardSession = (forceNew = false, projectId = null) => {
  const params = new URLSearchParams()
  if (forceNew) params.set('force_new', 'true')
  if (projectId) params.set('project_id', projectId)
  const qs = params.toString()
  return request(`/brand-voice/wizard/start${qs ? '?' + qs : ''}`, { method: 'POST' })
}
export const getWizardSession = (sessionId) => request(`/brand-voice/wizard/${sessionId}`)
export const answerWizardQuestion = (sessionId, phase, questionId, answer) =>
  request(`/brand-voice/wizard/${sessionId}/answer`, {
    method: 'POST',
    body: { phase, question_id: questionId, answer },
  })
export const synthesizeWizardPhase = (sessionId, phase) =>
  request(`/brand-voice/wizard/${sessionId}/synthesize-phase`, { method: 'POST', body: { phase } })
export const finalizeWizardSession = (sessionId) =>
  request(`/brand-voice/wizard/${sessionId}/finalize`, { method: 'POST' })

export const patchBrandVoiceField = (tenantId, profileType, fieldPath, newValue) =>
  request(`/brand-voice/${tenantId}/${profileType}/field`, {
    method: 'PATCH',
    body: { field_path: fieldPath, new_value: newValue },
  })
export const getBrandVoiceHistory = (tenantId) => getBrandVoiceStatus(tenantId)

// Drift Review (#78)
export function getDriftObservations(tenantId = 'me', status = 'pending_review') {
  return request('/brand-voice/drift-observations', {
    params: { tenant_id: tenantId, status },
  })
}

export function decideDriftObservation(observationId, changes) {
  return request(`/brand-voice/drift-observations/${observationId}/decide`, {
    method: 'POST',
    body: { changes },
  })
}

// Review Queue (#83)
export function getReviewQueue(tenantId = 'me', status = 'pending') {
  return request('/brand-voice/review-queue', { params: { tenant_id: tenantId, status } })
}

export function decideReviewQueueItem(queueId, action, note = '') {
  return request(`/brand-voice/review-queue/${queueId}/decide`, {
    method: 'POST',
    body: { action, note },
  })
}

// Admin Models (#80)

export function listAdminModels(adminToken) {
  return request('/admin/models', { headers: { 'X-Admin-Token': adminToken } })
}

export function startBacktest(adminToken, tenantId, candidateModelId, postCount = 10) {
  return request('/admin/models/backtest', {
    method: 'POST',
    headers: { 'X-Admin-Token': adminToken },
    body: { tenant_id: tenantId, candidate_model_id: candidateModelId, post_count: postCount },
  })
}

export function getBacktest(adminToken, runId) {
  return request(`/admin/models/backtest/${runId}`, { headers: { 'X-Admin-Token': adminToken } })
}

export function notifyTenantModel(adminToken, tenantId, backtestRunId) {
  return request('/admin/models/notify-tenant', {
    method: 'POST',
    headers: { 'X-Admin-Token': adminToken },
    body: { tenant_id: tenantId, backtest_run_id: backtestRunId },
  })
}

export function applyTenantModel(adminToken, tenantId, modelId) {
  const qs = new URLSearchParams({ tenant_id: tenantId, model_id: modelId }).toString()
  return request(`/admin/models/apply-tenant-model?${qs}`, {
    method: 'POST',
    headers: { 'X-Admin-Token': adminToken },
  })
}

// LLM Analytics
export const getLLMAnalyticsSummary = (params) => request('/analytics/llm-summary', { params })
export const getLLMAnalyticsByTask = (params) => request('/analytics/llm-by-task', { params })
export const getLLMAnalyticsByModel = (params) => request('/analytics/llm-by-model', { params })
export const getLLMAnalyticsByDay = (params) => request('/analytics/llm-by-day', { params })
export const getLLMAnalyticsByHour = (params) => request('/analytics/llm-by-hour', { params })
export const getContentByCategory = (params) =>
  request('/analytics/content-by-category', { params })
export const getTenantIndustry = () => request('/tenants/me/industry')
export const setTenantIndustry = (industry) =>
  request('/tenants/me/industry', { method: 'PUT', body: { industry } })
export const refreshIndustry = () => request('/tenants/me/industry/refresh', { method: 'POST' })
export const listHooks = (params) => request('/hooks/library', { params })
export const importHooks = (limit = 20) =>
  request(`/hooks/library/import?limit=${limit}`, { method: 'POST' })
export const addManualHook = (hook_text, hook_type = 'manual') =>
  request('/hooks/library', { method: 'POST', body: { hook_text, hook_type } })
export const deleteHook = (id) => request(`/hooks/library/${id}`, { method: 'DELETE' })

export const listResearchFindings = (params) => request('/research/findings', { params })
export const dismissResearchFinding = (id) =>
  request(`/research/findings/${id}/dismiss`, { method: 'POST' })
export const markFindingAsIdea = (id, hookIdx) =>
  request(`/research/findings/${id}/use-as-idea?hook_index=${hookIdx}`, { method: 'POST' })

export const listIdeaVariants = (ideaId) => request(`/ideas/${ideaId}/variants`)
export const regenerateIdeaVariants = (ideaId) =>
  request(`/ideas/${ideaId}/variants/regenerate`, { method: 'POST' })
export const chooseIdeaVariant = (ideaId, variantId) =>
  request(`/ideas/${ideaId}/variants/${variantId}/choose`, { method: 'POST' })
export const searchMemory = (params) => request('/memory/search', { params })
export const getMemoryRecent = (params) => request('/memory/recent', { params })
export const getMemoryPicker = (params) => request('/memory/picker', { params })
export const getMemoryStats = () => request('/memory/stats')
export const addMemoryNote = (data) => request('/memory/note', { method: 'POST', body: data })

export const getCompanyProfile = () => request('/me/company-profile')
export const updateCompanyProfile = (fields) =>
  request('/me/company-profile', { method: 'PUT', body: fields })
export const getCompanyProvenance = () => request('/me/company-profile/provenance')
export const getCompanyProfilePending = () => request('/me/company-profile/pending')
export const reviewCompanyProfileSuggestion = (id, action) =>
  request(`/me/company-profile/review/${id}`, { method: 'POST', body: { action } })
export const importCompanyProfileMd = (content, auto_apply = true) =>
  request('/me/company-profile/import-md', { method: 'POST', body: { content, auto_apply } })

export const requestDataDeletion = (payload) =>
  request('/me/data-deletion', { method: 'POST', body: payload })
export const listDataDeletions = () => request('/me/data-deletion')
export const recoverDataDeletion = (id) =>
  request(`/me/data-deletion/${id}/recover`, { method: 'POST' })
export const getDataDeletion = (id) => request(`/me/data-deletion/${id}`)
export const getMemoryVizData = (params) => request('/memory/viz-data', { params })
// Critical #3: Volltext nach explizitem Confirm (POST, schreibt Audit-Log)
export const getMemoryChunkFullText = (chunkId, reason) =>
  request(`/memory/viz-data/${chunkId}/full`, { method: 'POST', body: { confirm: true, reason } })
export const getLLMAnalyticsAnomaly = (params) => request('/analytics/llm-anomaly', { params })

// Prompt-Studio (P3)
export const getPromptFiles = () => request('/prompt-studio/files')
export const getPromptFile = (path) => request(`/prompt-studio/files/${path}`)
export const validatePromptFile = (path, content) =>
  request(`/prompt-studio/files/${path}/validate`, { method: 'POST', body: { content } })
export const savePromptFile = (path, content, baseSha) =>
  request(`/prompt-studio/files/${path}`, {
    method: 'PUT',
    body: { content, base_sha256: baseSha },
  })
export const revertPromptFile = (path) =>
  request(`/prompt-studio/files/${path}/overlay`, { method: 'DELETE' })

// #155 Cost-Monitoring: Trend, Cache-Hit-Rate, Runaway-Detection
export const getCostTrend = (params) => request('/analytics/cost-trend', { params })
export const getCacheHitRate = (params) => request('/analytics/cache-hit-rate', { params })
export const getRunawayDetection = (params) => request('/analytics/runaway-detection', { params })

export const getLLMAnalyticsCSVUrl = (params) => {
  const base = window.location.origin
  const qs = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== ''))
  ).toString()
  return `${base}/api/analytics/llm-calls.csv${qs ? '?' + qs : ''}`
}

// Quality-Gate Eval History (#152)
export const getQualityGateEvalHistory = (params) =>
  request('/eval/quality-gate/history', { params })
export const getQualityGateEvalLatest = () => request('/eval/quality-gate/latest')

// Throttle Status (#156)
export function getThrottleStatus(adminToken, tenantId) {
  const qs = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''
  return request(`/admin/throttle-status${qs}`, {
    headers: { 'X-Admin-Token': adminToken },
  })
}

// Telegram-Bot (pro Projekt/Tenant)
export const getTelegramBot = () => request('/tenants/me/telegram-bot')
export const setTelegramBot = (token) =>
  request('/tenants/me/telegram-bot', { method: 'POST', body: { token } })
export const revokeTelegramBot = () =>
  request('/tenants/me/telegram-bot', { method: 'DELETE' })
export const getTelegramUsers = () => request('/tenants/me/telegram-users')
export const blockTelegramUser = (userId) =>
  request(`/tenants/me/telegram-users/${userId}/block`, { method: 'POST' })
export const unblockTelegramUser = (userId) =>
  request(`/tenants/me/telegram-users/${userId}/unblock`, { method: 'POST' })
export const removeTelegramUser = (userId) =>
  request(`/tenants/me/telegram-users/${userId}`, { method: 'DELETE' })
export const manualLinkTelegramUser = (data) =>
  request('/tenants/me/telegram-users/manual-link', { method: 'POST', body: data })

// ── Admin-Session API (#98) ──────────────────────────────────────────────────
// Diese Endpunkte nutzen HttpOnly-Cookie `admin_session` statt X-API-Key.
// credentials:'include' ist erforderlich damit der Browser das Cookie mitsendet.
// State-ändernde Calls (POST/PUT) brauchen X-CSRF-Token (Double-Submit-Cookie).
// CSRF-Middleware exemptiert Requests MIT X-API-Key — admin-Calls haben keinen,
// daher müssen wir den Token explizit holen und im Header mitsenden.

async function getAdminCsrfToken() {
  // GET /api/csrf-token setzt csrf_token-Cookie und gibt {csrf_token} zurück.
  const resp = await fetch(`${API_BASE}/csrf-token`, { credentials: 'include' })
  if (!resp.ok) throw new Error('CSRF-Token konnte nicht geladen werden')
  const data = await resp.json()
  return data.csrf_token
}

async function adminRequest(path, options = {}) {
  const { method = 'GET', body } = options
  const url = `${API_BASE}${path}`
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'

  // Für state-ändernde Methoden CSRF-Token holen
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrfToken = await getAdminCsrfToken()
    headers['X-CSRF-Token'] = csrfToken
  }

  const resp = await fetch(url, {
    method,
    headers,
    credentials: 'include', // HttpOnly-Cookie admin_session mitsenden
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    let msg = err.detail
    if (typeof msg !== 'string') {
      msg = (err.detail && (err.detail.message || err.detail.error)) || JSON.stringify(err.detail)
    }
    const e = new Error(msg || 'Admin API Error')
    e.status = resp.status
    e.detail = err.detail
    throw e
  }
  return resp.json()
}

export const adminSession = () => adminRequest('/admin/session')
export const adminLogin = (username, password) =>
  adminRequest('/admin/login', { method: 'POST', body: { username, password } })
export const adminLogout = () => adminRequest('/admin/logout', { method: 'POST' })
export const adminListUsers = () => adminRequest('/admin/users')
export const adminRegenerateApiKey = (id) =>
  adminRequest(`/admin/users/${id}/regenerate-api-key`, { method: 'POST' })
export const adminSetApiKey = (id, key) =>
  adminRequest(`/admin/users/${id}/api-key`, { method: 'PUT', body: { api_key: key } })
export const adminCreateUser = (name) =>
  adminRequest('/admin/users', { method: 'POST', body: { name } })

// Modell-Modus-Switch (Issue #72)
export const getModelMode = () => request('/tenants/me/model-mode')
export const setModelMode = (model_mode) =>
  request('/tenants/me/model-mode', { method: 'PUT', body: { model_mode } })
