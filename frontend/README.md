# Synaps - AI-Powered Log Analysis Frontend

React + TypeScript frontend for the AI-Powered Log Analysis Platform.

## Features

- **Dashboard Overview**: Real-time metrics, system health monitoring, and critical anomalies
- **Real-time Log Stream**: Live log viewing with WebSocket support and advanced filtering
- **Semantic Search & Analysis**: AI-powered log search using vector embeddings
- **Reports & Trends**: View AI-generated analysis reports and historical trends
- **Responsive Design**: Mobile-first design with dark mode support

## Tech Stack

- **React 19** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool
- **Tailwind CSS v4** - Styling
- **React Router** - Routing
- **TanStack Query** - Data fetching and caching
- **Axios** - HTTP client
- **Recharts** - Data visualization
- **date-fns** - Date formatting

## Prerequisites

- Node.js 18+
- npm or yarn
- Backend API running on `http://localhost:8005` (see main project README)

## Quick Start

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Environment Variables

Create a `.env` file in the frontend directory:

```bash
cp .env.example .env
```

Edit `.env` to match your backend configuration:

```env
VITE_API_URL=http://localhost:8005
VITE_WS_URL=ws://localhost:8005
```

### 3. Start Development Server

```bash
npm run dev
```

The app will be available at `http://localhost:5173`

### 4. Build for Production

```bash
npm run build
npm run preview  # Preview the production build
```

## Project Structure

```
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts           # API client with all endpoints
│   │   ├── types.ts            # TypeScript type definitions
│   │   └── mock.ts             # Mock data for development
│   ├── components/
│   │   ├── layout/
│   │   │   ├── DashboardLayout.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── TopBar.tsx
│   │   ├── ui/
│   │   │   └── MetricCard.tsx
│   │   └── charts/
│   │       └── MainChart.tsx
│   ├── pages/
│   │   ├── Overview.tsx        # Dashboard overview page
│   │   ├── LogStream.tsx       # Real-time log stream
│   │   ├── SemanticSearch.tsx  # AI-powered search
│   │   └── Reports.tsx         # Analysis reports
│   ├── App.tsx                 # Main app component
│   ├── main.tsx               # App entry point
│   └── index.css              # Global styles
├── public/                    # Static assets
├── .env.example              # Environment variables template
├── package.json              # Dependencies and scripts
├── tailwind.config.js        # Tailwind configuration
├── vite.config.ts           # Vite configuration
└── tsconfig.json            # TypeScript configuration
```

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint

## API Integration

The frontend integrates with the following backend services:

| Service | Port | Purpose |
|---------|------|---------|
| API Gateway | 8005 | Unified REST API |
| Log Generator | 8000 | Control log generation |
| Kafka Consumer | 8001 | Consumer stats |
| LLM Analyzer | 8002 | Trigger analysis, view reports |
| Jina Embeddings | 8003 | Embedding stats |
| Vectorization Worker | 8004 | Vectorization stats |

### Key API Endpoints

**Dashboard**:
- `GET /api/metrics` - System metrics
- `GET /health` - Service health
- `GET /api/anomalies` - Recent anomalies

**Log Stream**:
- `WS /api/ws/logs` - WebSocket for real-time logs

**Semantic Search**:
- `POST /api/search/semantic` - Vector similarity search

**Reports**:
- `GET /api/reports` - Analysis reports
- `GET http://localhost:8002/reports/latest` - Latest report

See [API_DOCUMENTATION.md](../documentation/API_DOCUMENTATION.md) for complete API reference.

## Features by Page

### Dashboard Overview

- **KPI Cards**: Total logs, error rate, cache hit rate, active anomalies
- **System Health**: Real-time status of all services (ClickHouse, PostgreSQL, Qdrant, Redis)
- **Throughput Chart**: Ingestion rate visualization
- **Critical Anomalies Table**: Recent high-severity anomalies
- **AI Insights**: Daily insights and recommendations

### Real-time Log Stream

- **Live WebSocket**: Real-time log streaming with auto-reconnection
- **Advanced Filtering**: Filter by log level, service, and search queries
- **Expandable Rows**: Click to view full log details in JSON format
- **Pause/Resume**: Control log flow
- **Performance**: Buffers last 100 logs for smooth scrolling

### Semantic Search & Analysis

- **Natural Language Queries**: Search using plain English
- **AI-Powered Results**: Vector similarity matching with Jina Embeddings
- **Similarity Scores**: Visual indicators of match quality
- **Detailed Analysis**: AI-generated summaries and insights
- **Pattern Recognition**: Identify related errors across services

### Reports & Trends

- **Latest Report Card**: Quick view of most recent analysis
- **Executive Summary**: AI-generated insights
- **Key Metrics**: Logs processed, errors found, patterns, anomalies
- **Recommendations**: Actionable suggestions from AI
- **Report History**: Browse past analysis reports

## Design System

### Colors

```javascript
primary: #facc15      // Lemon Yellow
primaryAlt: #2badee   // Electric Blue
backgroundDark: #101c22
panelDark: #16232b
borderDark: #233c48
textMuted: #92b7c9
success: #22c55e
warning: #f97316
error: #facc15
```

### Fonts

- **Display**: Manrope - Headings and UI elements
- **Body**: Noto Sans - Body text
- **Mono**: JetBrains Mono - Code and log messages

### Icons

Material Symbols Outlined from Google Fonts

## WebSocket Integration

The Real-time Log Stream page uses WebSocket for live updates:

```typescript
// Auto-connects on mount
const client = new LogStreamClient(
  (log) => console.log('New log:', log),
  (error) => console.error('Error:', error),
  () => console.log('Connected'),
  () => console.log('Disconnected')
);

client.connect(); // Connect to ws://localhost:8005/api/ws/logs
```

Features:
- Automatic reconnection (up to 5 attempts)
- Exponential backoff
- Connection status indicator
- Pause/resume log flow

## Development Tips

### Using Mock Data

For development without backend:

```typescript
import { mockApi } from './api/mock';

// Use mock instead of real API
const { data } = useQuery({
  queryKey: ['overview'],
  queryFn: mockApi.getOverview // Instead of api.getMetrics
});
```

### Hot Module Replacement

Vite supports HMR - changes are reflected instantly without full page reload.

### TypeScript

All API responses are fully typed. Check `src/api/client.ts` for type definitions.

## Troubleshooting

### Backend Connection Issues

If you see connection errors:

1. Verify backend is running: `docker compose ps`
2. Check API URL in `.env`: `VITE_API_URL=http://localhost:8005`
3. Check CORS is enabled on backend
4. View browser console for detailed errors

### WebSocket Not Connecting

1. Verify WebSocket URL: `VITE_WS_URL=ws://localhost:8005`
2. Check API Gateway is running on port 8005
3. Look for connection errors in browser console
4. Try refreshing the page

### Styling Issues

1. Ensure Tailwind CSS is properly configured
2. Clear build cache: `rm -rf node_modules/.vite`
3. Restart dev server

### Build Errors

1. Clear dependencies: `rm -rf node_modules && npm install`
2. Check TypeScript errors: `npx tsc --noEmit`
3. Update dependencies: `npm update`

## Performance Optimization

- **React Query**: Automatic caching and background updates
- **Code Splitting**: Routes are lazy-loaded
- **Debounced Search**: Search queries are debounced to reduce API calls
- **Memoization**: Expensive computations are memoized
- **Virtual Scrolling**: Consider for large log lists (future enhancement)

## Browser Support

- Chrome/Edge (latest 2 versions)
- Firefox (latest 2 versions)
- Safari (latest 2 versions)

## Contributing

1. Follow existing code style
2. Use TypeScript for type safety
3. Write descriptive commit messages
4. Test on multiple browsers
5. Update documentation as needed

## License

MIT License - See main project LICENSE file

---
