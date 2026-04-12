import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Badge } from './ui/Badge'
import { useApi } from '../hooks/useApi'
import { getDashboard } from '../api'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const statLabels = {
  new_videos: 'Neue Videos (24h)',
  processing: 'In Verarbeitung',
  content_suggestions: 'Content-Vorschlaege',
  approved: 'Freigegeben',
}

const statColors = {
  new_videos: 'text-blue-600',
  processing: 'text-yellow-600',
  content_suggestions: 'text-purple-600',
  approved: 'text-green-600',
}

export default function Dashboard() {
  const { data, loading, error } = useApi(getDashboard)

  if (loading) return <div className="text-gray-500">Lade Dashboard...</div>
  if (error) return <div className="text-red-500">Fehler: {error}</div>

  const { stats, weekly_videos, recent_content, active_sources } = data

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h2>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {Object.entries(stats).map(([key, value]) => (
          <Card key={key}>
            <CardContent className="py-5">
              <p className="text-sm text-gray-500 dark:text-gray-400">{statLabels[key]}</p>
              <p className={`text-3xl font-bold mt-1 ${statColors[key]}`}>{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Weekly Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Videos pro Woche</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={weekly_videos}>
                  <XAxis dataKey="week" fontSize={12} />
                  <YAxis fontSize={12} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} name="Videos" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Active Sources */}
        <Card>
          <CardHeader>
            <CardTitle>Aktive Quellen</CardTitle>
          </CardHeader>
          <CardContent>
            {active_sources.length === 0 ? (
              <p className="text-sm text-gray-500">Noch keine Quellen konfiguriert.</p>
            ) : (
              <div className="space-y-3">
                {active_sources.map(s => (
                  <div key={s.id} className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{s.name}</p>
                      <p className="text-xs text-gray-500">{s.type}</p>
                    </div>
                    <div className="text-right">
                      <Badge color={s.is_active ? 'green' : 'gray'}>{s.is_active ? 'Aktiv' : 'Inaktiv'}</Badge>
                      {s.last_checked_at && (
                        <p className="text-xs text-gray-400 mt-1">
                          {new Date(s.last_checked_at).toLocaleString('de-DE')}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Content */}
      <Card>
        <CardHeader>
          <CardTitle>Letzte Content-Vorschlaege</CardTitle>
        </CardHeader>
        <CardContent>
          {recent_content.length === 0 ? (
            <p className="text-sm text-gray-500">Noch kein Content generiert.</p>
          ) : (
            <div className="space-y-3">
              {recent_content.map(c => (
                <div key={c.id} className="flex items-start gap-3 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                  <Badge color="blue">{c.channel}</Badge>
                  <p className="text-sm text-gray-700 dark:text-gray-300 flex-1">{c.content_text}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
