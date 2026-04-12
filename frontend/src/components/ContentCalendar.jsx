import { useState, useMemo } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { useApi } from '../hooks/useApi'
import { getContentList } from '../api'

const DAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
const MONTHS = ['Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

export default function ContentCalendar() {
  const [currentDate, setCurrentDate] = useState(new Date())
  const { data: content, loading } = useApi(() => getContentList({ status: 'scheduled' }))

  const year = currentDate.getFullYear()
  const month = currentDate.getMonth()
  const firstDay = new Date(year, month, 1)
  const lastDay = new Date(year, month + 1, 0)

  // Monday = 0 in our grid
  const startOffset = (firstDay.getDay() + 6) % 7

  const days = useMemo(() => {
    const result = []
    for (let i = 0; i < startOffset; i++) result.push(null)
    for (let d = 1; d <= lastDay.getDate(); d++) result.push(d)
    return result
  }, [year, month])

  const getContentForDay = (day) => {
    if (!content || !day) return []
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    return content.filter(c => c.scheduled_for && c.scheduled_for.startsWith(dateStr))
  }

  const navigate = (dir) => {
    setCurrentDate(new Date(year, month + dir, 1))
  }

  if (loading) return <div className="text-gray-500">Lade Kalender...</div>

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Content-Kalender</h2>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>&larr;</Button>
          <CardTitle>{MONTHS[month]} {year}</CardTitle>
          <Button variant="ghost" size="sm" onClick={() => navigate(1)}>&rarr;</Button>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-7 gap-1">
            {DAYS.map(d => (
              <div key={d} className="text-center text-xs font-semibold text-gray-500 py-2">{d}</div>
            ))}
            {days.map((day, i) => {
              const dayContent = getContentForDay(day)
              const isToday = day && new Date().getDate() === day && new Date().getMonth() === month && new Date().getFullYear() === year
              return (
                <div
                  key={i}
                  className={`min-h-[80px] p-1 border border-gray-100 dark:border-gray-800 rounded ${
                    day ? 'bg-white dark:bg-gray-900' : 'bg-gray-50 dark:bg-gray-950'
                  } ${isToday ? 'ring-2 ring-primary-500' : ''}`}
                >
                  {day && (
                    <>
                      <span className={`text-xs font-medium ${isToday ? 'text-primary-600' : 'text-gray-500'}`}>{day}</span>
                      <div className="mt-1 space-y-1">
                        {dayContent.map(c => (
                          <div key={c.id} className="text-xs">
                            <Badge color="blue">{c.channel}</Badge>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
