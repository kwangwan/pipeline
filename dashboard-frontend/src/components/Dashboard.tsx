import { useEffect, useState } from 'react'
import axios from 'axios'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
} from 'chart.js'
import { Line, Bar, Doughnut } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend
)

const API_Base = 'http://localhost:8000'

interface StatItem {
    time?: string
    publisher?: string
    section?: string
    count: number
}

interface FilterOptions {
    publishers: string[]
    sections: string[]
}

interface SummaryStats {
    total: number
    success: number
    failed: number
}

function Dashboard() {
  const [trendData, setTrendData] = useState<StatItem[]>([])
  const [publisherData, setPublisherData] = useState<StatItem[]>([])
  const [sectionData, setSectionData] = useState<StatItem[]>([])
  const [period, setPeriod] = useState<'hourly' | 'daily'>('daily')
  const [summary, setSummary] = useState<SummaryStats>({ total: 0, success: 0, failed: 0 })
  const [filters, setFilters] = useState<FilterOptions>({ publishers: [], sections: [] })
  
  // Filter States
  const [selectedPublisher, setSelectedPublisher] = useState('')
  const [selectedSection, setSelectedSection] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [dateField, setDateField] = useState<'created_at' | 'article_date'>('created_at')

  useEffect(() => {
    fetchFilters()
  }, [])

  useEffect(() => {
    fetchData()
  }, [period, selectedPublisher, selectedSection, startDate, endDate, dateField])

  const fetchFilters = async () => {
      try {
          const res = await axios.get(`${API_Base}/filters`)
          setFilters(res.data)
      } catch (err) {
          console.error(err)
      }
  }

  const fetchData = () => {
      const params = new URLSearchParams()
      if (period) params.append('period', period)
      if (selectedPublisher) params.append('publisher', selectedPublisher)
      if (selectedSection) params.append('section', selectedSection)
      if (startDate) params.append('start_date', startDate)
      if (endDate) params.append('end_date', endDate)

      const trendParams = new URLSearchParams(params)
      trendParams.append('date_field', dateField)

      axios.get(`${API_Base}/stats/trend?${trendParams.toString()}`).then(res => setTrendData(res.data))
      
      const queryString = params.toString()
      axios.get(`${API_Base}/stats/publisher?${queryString}`).then(res => setPublisherData(res.data))
      axios.get(`${API_Base}/stats/section?${queryString}`).then(res => setSectionData(res.data))
      axios.get(`${API_Base}/stats/summary?${queryString}`).then(res => setSummary(res.data))
  }

  const trendChartData = {
    labels: trendData.map((d) => {
        const date = new Date(d.time!)
        if (isNaN(date.getTime())) return 'Unknown'
        return period === 'hourly' 
            ? date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})
            : date.toLocaleDateString()
    }),
    datasets: [
      {
        label: dateField === 'article_date' ? 'Articles (by Published Date)' : 'Articles (by Collected Date)',
        data: trendData.map((d) => d.count),
        borderColor: '#38bdf8',
        backgroundColor: 'rgba(56, 189, 248, 0.5)',
        tension: 0.3,
      },
    ],
  }

  const publisherChartData = {
    labels: publisherData.map((d) => d.publisher),
    datasets: [
      {
        label: 'Articles by Publisher',
        data: publisherData.map((d) => d.count),
        backgroundColor: '#818cf8',
      },
    ],
  }

    const sectionChartData = {
    labels: sectionData.map((d) => d.section),
    datasets: [
      {
        label: 'Articles by Section',
        data: sectionData.map((d) => d.count),
        backgroundColor: [
            '#34d399', '#febf3a', '#f87171', '#60a5fa', '#a78bfa', '#fb923c'
        ],
      },
    ],
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 bg-slate-900 min-h-screen text-slate-100">
      <header className="flex flex-col md:flex-row justify-between items-center gap-4">
        <h1 className="text-3xl font-bold bg-gradient-to-r from-sky-400 to-indigo-500 bg-clip-text text-transparent">
          News Collection Dashboard
        </h1>
        <div className="flex gap-2">
             <button 
                onClick={() => setPeriod('hourly')}
                className={`px-4 py-2 rounded-lg transition-colors ${period === 'hourly' ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'}`}
             >
                Hourly
             </button>
             <button 
                onClick={() => setPeriod('daily')}
                className={`px-4 py-2 rounded-lg transition-colors ${period === 'daily' ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'}`}
             >
                Daily
             </button>
        </div>
      </header>

      {/* Filters */}
      <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 flex flex-wrap gap-4 items-end">
          <div className="flex flex-col gap-1">
              <label className="text-sm text-slate-400">Start Date</label>
              <input 
                type="date" 
                className="bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white focus:outline-none focus:border-sky-500"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
          </div>
          <div className="flex flex-col gap-1">
              <label className="text-sm text-slate-400">End Date</label>
              <input 
                type="date" 
                className="bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white focus:outline-none focus:border-sky-500"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
          </div>
           <div className="flex flex-col gap-1">
              <label className="text-sm text-slate-400">Publisher</label>
              <select 
                className="bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white focus:outline-none focus:border-sky-500"
                value={selectedPublisher}
                onChange={(e) => setSelectedPublisher(e.target.value)}
              >
                  <option value="">All Publishers</option>
                  {filters.publishers.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
          </div>
           <div className="flex flex-col gap-1">
              <label className="text-sm text-slate-400">Section</label>
              <select 
                className="bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white focus:outline-none focus:border-sky-500"
                value={selectedSection}
                onChange={(e) => setSelectedSection(e.target.value)}
              >
                  <option value="">All Sections</option>
                  {filters.sections.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
          </div>
          <button 
            className="px-4 py-2 bg-slate-600 hover:bg-slate-500 rounded text-white ml-auto"
            onClick={() => {
                setStartDate('')
                setEndDate('')
                setSelectedPublisher('')
                setSelectedSection('')
            }}
          >
              Reset Filters
          </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg">
              <h3 className="text-slate-400 text-sm font-medium uppercase">Total Articles</h3>
              <p className="text-4xl font-bold text-white mt-2">{summary.total.toLocaleString()}</p>
          </div>
          <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg">
              <h3 className="text-slate-400 text-sm font-medium uppercase">Success</h3>
              <p className="text-4xl font-bold text-green-400 mt-2">{summary.success ? summary.success.toLocaleString() : 0}</p>
          </div>
          <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg relative group">
              <h3 className="text-slate-400 text-sm font-medium uppercase">Failed</h3>
              <p className="text-4xl font-bold text-red-400 mt-2">{summary.failed ? summary.failed.toLocaleString() : 0}</p>
              {summary.failed > 0 && (
                  <button 
                    className="absolute top-4 right-4 text-xs bg-red-600 hover:bg-red-500 text-white px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={async () => {
                        if (window.confirm('Reset all failed articles to PENDING?')) {
                            try {
                                await axios.post(`${API_Base}/articles/reset-failed`)
                                fetchData()
                            } catch (err) {
                                console.error(err)
                                alert('Failed to reset articles')
                            }
                        }
                    }}
                  >
                      Reset
                  </button>
              )}
          </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Trend Chart */}
        <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg lg:col-span-2">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
                <h2 className="text-xl font-semibold text-slate-200">
                    {dateField === 'article_date' ? 'Article Publication Trend' : 'Data Collection Trend'}
                </h2>
                <div className="flex bg-slate-700 p-1 rounded-lg">
                    <button 
                        onClick={() => setDateField('created_at')}
                        className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${dateField === 'created_at' ? 'bg-sky-600 text-white shadow-lg' : 'text-slate-400 hover:text-slate-200'}`}
                    >
                        Created At
                    </button>
                    <button 
                        onClick={() => setDateField('article_date')}
                        className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${dateField === 'article_date' ? 'bg-sky-600 text-white shadow-lg' : 'text-slate-400 hover:text-slate-200'}`}
                    >
                        Article Date
                    </button>
                </div>
            </div>
            <div className="h-64 sm:h-80">
                <Line 
                    data={trendChartData} 
                    options={{ 
                        responsive: true, 
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { grid: { color: '#334155' } },
                            x: { grid: { display: false } }
                        }
                    }} 
                />
            </div>
        </div>

        {/* Publisher Chart */}
         <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg">
            <h2 className="text-xl font-semibold mb-4 text-slate-200">Top Publishers</h2>
             <div className="h-64">
                <Bar 
                    data={publisherChartData}
                    options={{
                        indexAxis: 'y',
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                         scales: {
                            x: { grid: { color: '#334155' } },
                            y: { grid: { display: false } }
                        }
                    }}
                />
            </div>
        </div>

        {/* Section Chart */}
         <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg">
            <h2 className="text-xl font-semibold mb-4 text-slate-200">Section Distribution</h2>
             <div className="h-64 flex justify-center">
                <Doughnut 
                    data={sectionChartData}
                    options={{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { position: 'right', labels: { color: '#cbd5e1' } } },
                    }}
                />
            </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
