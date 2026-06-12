import { useState, useEffect } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Calendar as CalIcon,
  Clock,
  Trash2,
  Plus,
  Check,
} from 'lucide-react'
import {
  getCalendar,
  getScheduledPosts,
  getContentList,
  schedulePost,
  cancelScheduledPost,
  updateScheduledPost,
} from '../api'

const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
const MONTHS_DE = [
  'Januar',
  'Februar',
  'März',
  'April',
  'Mai',
  'Juni',
  'Juli',
  'August',
  'September',
  'Oktober',
  'November',
  'Dezember',
]

const STATUS_BADGE = {
  scheduled: 'bg-blue-100 text-blue-700',
  published: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
}

const ANGLE_COLORS = {
  meinung: 'bg-purple-100 text-purple-800',
  howto: 'bg-teal-100 text-teal-800',
  story: 'bg-amber-100 text-amber-800',
  kontroverse: 'bg-red-100 text-red-800',
  statistik: 'bg-blue-100 text-blue-800',
  trend: 'bg-emerald-100 text-emerald-800',
}

function CalendarDay({ day, posts, isToday, isCurrentMonth, onDayClick, onPostClick }) {
  return (
    <div
      onClick={() => isCurrentMonth && onDayClick(day)}
      className={`min-h-[80px] p-1.5 border-b border-r border-gray-100 transition-colors ${
        !isCurrentMonth
          ? 'bg-gray-50'
          : isToday
            ? 'bg-primary-50 border-primary-200'
            : 'bg-white hover:bg-gray-50 cursor-pointer'
      }`}
    >
      <span
        className={`text-xs font-medium block mb-1 w-6 h-6 flex items-center justify-center rounded-full ${
          isToday ? 'bg-primary-700 text-white' : isCurrentMonth ? 'text-ink' : 'text-gray-300'
        }`}
      >
        {day}
      </span>
      <div className="space-y-0.5">
        {posts.map((p) => {
          const angle = p.angle
          const angleColor = angle
            ? ANGLE_COLORS[angle] || 'bg-primary-100 text-primary-800'
            : 'bg-primary-100 text-primary-800'
          const preview = p.content_preview || ''
          const time = new Date(p.scheduled_at).toLocaleTimeString('de-DE', {
            hour: '2-digit',
            minute: '2-digit',
          })
          return (
            <div
              key={p.id}
              onClick={(e) => {
                e.stopPropagation()
                onPostClick(p)
              }}
              className={`text-[10px] px-1.5 py-1 rounded ${angleColor} cursor-pointer hover:opacity-80 leading-tight`}
              title={preview || p.scheduled_at}
            >
              <div className="font-semibold">
                {time}
                {angle ? ` · ${angle}` : ''}
              </div>
              {preview && <div className="truncate opacity-80 mt-0.5">{preview.slice(0, 35)}</div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ScheduleModal({ selectedDate, posts, onClose, onScheduled }) {
  const [content, setContent] = useState([])
  const [selectedContent, setSelectedContent] = useState('')
  const [selectedTime, setSelectedTime] = useState('09:00')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    getContentList({ status: 'approved', limit: 50 })
      .then((data) => {
        setContent(Array.isArray(data) ? data : [])
      })
      .catch(() => {})
  }, [])

  async function handleSchedule() {
    if (!selectedContent) return
    setSaving(true)
    try {
      const dt = new Date(`${selectedDate}T${selectedTime}:00`)
      await schedulePost({
        content_piece_id: selectedContent,
        scheduled_at: dt.toISOString(),
      })
      setMessage({ type: 'success', text: 'Post eingeplant!' })
      setTimeout(() => {
        onClose()
        onScheduled()
      }, 1200)
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
    setSaving(false)
  }

  const dateLabel = new Date(selectedDate + 'T12:00').toLocaleDateString('de-DE', {
    weekday: 'long',
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  })

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="p-5 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-ink">Post einplanen</h3>
            <p className="text-xs text-ink-muted mt-0.5">{dateLabel}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 text-xl"
          >
            ×
          </button>
        </div>

        {/* Existing posts on this day */}
        {posts.length > 0 && (
          <div className="px-5 pt-4">
            <p className="text-xs font-semibold text-ink-muted mb-2">Bereits eingeplant:</p>
            <div className="space-y-1.5">
              {posts.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between text-xs bg-gray-50 rounded-lg px-3 py-2"
                >
                  <span className="text-ink">
                    {new Date(p.scheduled_at).toLocaleTimeString('de-DE', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}{' '}
                    Uhr
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${STATUS_BADGE[p.status] || 'bg-gray-100 text-gray-600'}`}
                  >
                    {p.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="p-5 space-y-4">
          <div>
            <label className="text-xs font-medium text-ink-light block mb-1.5">
              Post auswählen
            </label>
            <select
              value={selectedContent}
              onChange={(e) => setSelectedContent(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">— Freigegebenen Post wählen —</option>
              {content.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.content_text?.slice(0, 60)}...
                </option>
              ))}
            </select>
            {content.length === 0 && (
              <p className="text-xs text-amber-600 mt-1">
                Keine freigegebenen Posts. Erst Posts freigeben.
              </p>
            )}
            {selectedContent &&
              (() => {
                const p = content.find((c) => c.id === selectedContent)
                return p ? (
                  <p className="text-xs text-ink-muted mt-1.5 italic line-clamp-2">
                    {p.content_text?.slice(0, 120)}...
                  </p>
                ) : null
              })()}
          </div>

          <div>
            <label className="text-xs font-medium text-ink-light block mb-1.5">Uhrzeit</label>
            <input
              type="time"
              value={selectedTime}
              onChange={(e) => setSelectedTime(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          {message && (
            <div
              className={`p-3 rounded-lg text-sm ${message.type === 'error' ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'}`}
            >
              {message.text}
            </div>
          )}
        </div>

        <div className="px-5 pb-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-ink-light border border-gray-200 rounded-lg hover:bg-gray-50"
          >
            Abbrechen
          </button>
          <button
            onClick={handleSchedule}
            disabled={saving || !selectedContent}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-primary-700 rounded-lg hover:bg-primary-800 disabled:opacity-40"
          >
            {saving ? (
              <Clock className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Check className="w-3.5 h-3.5" />
            )}
            Einplanen
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Calendar() {
  const today = new Date()
  const [currentYear, setCurrentYear] = useState(today.getFullYear())
  const [currentMonth, setCurrentMonth] = useState(today.getMonth()) // 0-indexed
  const [calendarData, setCalendarData] = useState({})
  const [scheduledList, setScheduledList] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedDay, setSelectedDay] = useState(null)
  const [selectedPost, setSelectedPost] = useState(null)

  const monthKey = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`

  useEffect(() => {
    loadData()
  }, [monthKey])

  async function loadData() {
    setLoading(true)
    try {
      const [cal, list] = await Promise.all([getCalendar(monthKey), getScheduledPosts()])
      setCalendarData(cal || {})
      setScheduledList(Array.isArray(list) ? list : [])
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  function prevMonth() {
    if (currentMonth === 0) {
      setCurrentMonth(11)
      setCurrentYear((y) => y - 1)
    } else setCurrentMonth((m) => m - 1)
  }
  function nextMonth() {
    if (currentMonth === 11) {
      setCurrentMonth(0)
      setCurrentYear((y) => y + 1)
    } else setCurrentMonth((m) => m + 1)
  }

  // Build calendar grid
  const firstDay = new Date(currentYear, currentMonth, 1)
  const lastDay = new Date(currentYear, currentMonth + 1, 0)
  // Monday-first: getDay() returns 0=Sun, so we offset
  const startOffset = (firstDay.getDay() + 6) % 7 // 0=Mon
  const daysInMonth = lastDay.getDate()

  const cells = []
  // Leading empty cells (previous month)
  for (let i = 0; i < startOffset; i++) {
    const prevDate = new Date(currentYear, currentMonth, 1 - (startOffset - i))
    cells.push({ day: prevDate.getDate(), isCurrentMonth: false, dateStr: null })
  }
  // Current month
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    cells.push({ day: d, isCurrentMonth: true, dateStr, posts: calendarData[dateStr] || [] })
  }
  // Trailing cells
  const remaining = 42 - cells.length
  for (let i = 1; i <= remaining; i++) {
    cells.push({ day: i, isCurrentMonth: false, dateStr: null })
  }

  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  const upcomingPosts = scheduledList
    .filter((p) => p.status === 'scheduled')
    .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at))

  async function handleCancel(postId) {
    try {
      await cancelScheduledPost(postId)
      setSelectedPost(null)
      loadData()
    } catch (e) {}
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink">Post-Kalender</h1>
          <p className="text-sm text-ink-light mt-0.5">
            Plane und überblicke deine LinkedIn-Posts.
          </p>
        </div>
        <div className="flex items-center gap-2 bg-white border border-surface-border rounded-xl px-4 py-2 shadow-sm">
          <button
            onClick={prevMonth}
            className="p-1 rounded hover:bg-gray-100 text-ink-muted hover:text-ink"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-sm font-semibold text-ink w-32 text-center">
            {MONTHS_DE[currentMonth]} {currentYear}
          </span>
          <button
            onClick={nextMonth}
            className="p-1 rounded hover:bg-gray-100 text-ink-muted hover:text-ink"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Calendar Grid */}
        <div className="lg:col-span-3 bg-white rounded-xl border border-surface-border shadow-sm overflow-hidden">
          {/* Weekday headers */}
          <div className="grid grid-cols-7 border-b border-gray-100">
            {WEEKDAYS.map((d) => (
              <div
                key={d}
                className="py-2 text-center text-xs font-semibold text-ink-muted border-r border-gray-100 last:border-r-0"
              >
                {d}
              </div>
            ))}
          </div>
          {/* Days grid */}
          {loading ? (
            <div className="py-16 text-center text-ink-muted text-sm">Lade Kalender...</div>
          ) : (
            <div className="grid grid-cols-7">
              {cells.map((cell, i) => (
                <CalendarDay
                  key={i}
                  day={cell.day}
                  posts={cell.posts || []}
                  isToday={cell.dateStr === todayStr}
                  isCurrentMonth={cell.isCurrentMonth}
                  onDayClick={(day) => {
                    const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
                    setSelectedDay(dateStr)
                  }}
                  onPostClick={setSelectedPost}
                />
              ))}
            </div>
          )}
        </div>

        {/* Sidebar — upcoming posts */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-surface-border shadow-sm p-4">
            <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
              <Clock className="w-4 h-4 text-primary-600" /> Nächste Posts
            </h3>
            {upcomingPosts.length === 0 ? (
              <p className="text-xs text-ink-muted">Keine geplanten Posts.</p>
            ) : (
              <div className="space-y-2">
                {upcomingPosts.slice(0, 8).map((p) => (
                  <div
                    key={p.id}
                    onClick={() => setSelectedPost(p)}
                    className="cursor-pointer p-2.5 rounded-lg border border-gray-100 hover:border-primary-200 hover:bg-primary-50 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-semibold text-primary-700">
                        {new Date(p.scheduled_at).toLocaleDateString('de-DE', {
                          weekday: 'short',
                          day: '2-digit',
                          month: '2-digit',
                        })}
                      </span>
                      <span className="text-[10px] text-ink-muted">
                        {new Date(p.scheduled_at).toLocaleTimeString('de-DE', {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}{' '}
                        Uhr
                      </span>
                    </div>
                    {p.content_preview ? (
                      <p className="text-[11px] text-ink line-clamp-2 leading-relaxed">
                        {p.content_preview}
                      </p>
                    ) : (
                      <p className="text-[11px] text-ink-light italic">Kein Inhalt geladen</p>
                    )}
                    {p.angle && (
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded mt-1 inline-block ${ANGLE_COLORS[p.angle] || 'bg-gray-100 text-gray-600'}`}
                      >
                        {p.angle}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-primary-50 rounded-xl border border-primary-200 p-4">
            <p className="text-xs font-semibold text-primary-800 mb-2">💡 Tipp</p>
            <p className="text-xs text-primary-700 leading-relaxed">
              Klicke auf einen Tag im Kalender um einen Post einzuplanen. Dienstag & Mittwoch 8-9
              Uhr sind optimal.
            </p>
          </div>
        </div>
      </div>

      {/* Post detail modal */}
      {selectedPost && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onClick={() => setSelectedPost(null)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-semibold text-ink mb-3">Geplanter Post</h3>
            <div className="space-y-2 mb-4">
              <div className="flex justify-between text-sm">
                <span className="text-ink-muted">Datum</span>
                <span className="font-medium">
                  {new Date(selectedPost.scheduled_at).toLocaleDateString('de-DE', {
                    weekday: 'long',
                    day: '2-digit',
                    month: 'long',
                  })}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-ink-muted">Uhrzeit</span>
                <span className="font-medium">
                  {new Date(selectedPost.scheduled_at).toLocaleTimeString('de-DE', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}{' '}
                  Uhr
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-ink-muted">Status</span>
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE[selectedPost.status] || 'bg-gray-100 text-gray-600'}`}
                >
                  {selectedPost.status}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-ink-muted">Post-ID</span>
                <span className="font-mono text-xs">
                  {selectedPost.content_piece_id?.slice(0, 12)}...
                </span>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setSelectedPost(null)}
                className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                Schließen
              </button>
              {selectedPost.status === 'scheduled' && (
                <button
                  onClick={() => handleCancel(selectedPost.id)}
                  className="flex items-center gap-1.5 px-3 py-2 text-sm text-red-700 border border-red-200 rounded-lg hover:bg-red-50"
                >
                  <Trash2 className="w-3.5 h-3.5" /> Löschen
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Schedule new post modal */}
      {selectedDay && (
        <ScheduleModal
          selectedDate={selectedDay}
          posts={calendarData[selectedDay] || []}
          onClose={() => setSelectedDay(null)}
          onScheduled={() => {
            setSelectedDay(null)
            loadData()
          }}
        />
      )}
    </div>
  )
}
