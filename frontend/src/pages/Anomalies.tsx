import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { api, type Anomaly } from '../api/client';
import { mockApi } from '../api/mock';
import { format, subHours, addHours } from 'date-fns';

// Toggle this to switch between mock and real API
const USE_MOCK_API = true;

export const Anomalies = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [serviceFilter, setServiceFilter] = useState<string>('all');
  
  // Track which anomaly is being acted upon
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  // Fetch anomalies with filters
  const { data: anomaliesData, isLoading } = useQuery({
    queryKey: ['anomalies', severityFilter, statusFilter, serviceFilter],
    queryFn: () => {
      const params: any = { limit: 50 };
      if (severityFilter !== 'all') params.severity = severityFilter;
      if (statusFilter !== 'all') params.status = statusFilter;
      if (serviceFilter !== 'all') params.service = serviceFilter;

      return USE_MOCK_API ? mockApi.getAnomalies(params) : api.getAnomalies(params);
    },
    refetchInterval: USE_MOCK_API ? false : 30000, // Refetch every 30s in production
  });

  const anomalies = anomaliesData?.anomalies || [];

  // Acknowledge anomaly mutation
  const acknowledgeMutation = useMutation({
    mutationFn: (alertId: string) => {
      setAcknowledgingId(alertId);
      return USE_MOCK_API ? mockApi.acknowledgeAnomaly(alertId) : api.acknowledgeAnomaly(alertId);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['anomalies'] });
      toast.success(`Anomaly "${data.anomaly_type}" has been acknowledged`, {
        icon: '✓',
      });
      setAcknowledgingId(null);
    },
    onError: (error: any) => {
      toast.error(`Failed to acknowledge anomaly: ${error.message}`, {
        icon: '✕',
      });
      setAcknowledgingId(null);
    },
  });

  // Resolve anomaly mutation
  const resolveMutation = useMutation({
    mutationFn: (alertId: string) => {
      setResolvingId(alertId);
      return USE_MOCK_API ? mockApi.resolveAnomaly(alertId) : api.resolveAnomaly(alertId);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['anomalies'] });
      toast.success(`Anomaly "${data.anomaly_type}" has been resolved`, {
        icon: '✓',
      });
      setResolvingId(null);
    },
    onError: (error: any) => {
      toast.error(`Failed to resolve anomaly: ${error.message}`, {
        icon: '✕',
      });
      setResolvingId(null);
    },
  });

  // Handle investigate action - navigate to semantic search
  const handleInvestigate = (anomaly: Anomaly) => {
    // Extract time range around detection (±1 hour)
    const detectedAt = new Date(anomaly.detected_at);
    const startTime = subHours(detectedAt, 1).toISOString();
    const endTime = addHours(detectedAt, 1).toISOString();

    // Determine log level based on severity
    const level = anomaly.severity === 'critical' || anomaly.severity === 'high' ? 'ERROR' : 'WARN';

    toast.loading('Preparing investigation...', { duration: 1000 });

    // Navigate to semantic search with state
    setTimeout(() => {
      navigate('/analysis', {
        state: {
          initialQuery: anomaly.description,
          initialFilters: {
            level,
            service: anomaly.service,
            timeRange: '2h',
            startTime,
            endTime,
          },
          fromAnomaly: true,
          anomalyId: anomaly.alert_id,
        },
      });
    }, 1000);
  };

  // Calculate statistics
  const criticalCount = anomalies.filter(a => a.severity === 'critical').length;
  const highCount = anomalies.filter(a => a.severity === 'high').length;
  const newCount = anomalies.filter(a => a.status === 'new').length;
  const avgConfidence = anomalies.length > 0
    ? (anomalies.reduce((sum, a) => sum + a.confidence_score, 0) / anomalies.length * 100)
    : 0;

  // Extract unique services for filter
  const uniqueServices = Array.from(new Set(anomalies.map(a => a.service)));

  // Severity color mapping
  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'text-red-400 bg-red-400/10 ring-red-400/20';
      case 'high': return 'text-orange-400 bg-orange-400/10 ring-orange-400/20';
      case 'medium': return 'text-yellow-400 bg-yellow-400/10 ring-yellow-400/20';
      case 'low': return 'text-blue-400 bg-blue-400/10 ring-blue-400/20';
      default: return 'text-gray-400 bg-gray-400/10 ring-gray-400/20';
    }
  };

  // Status color mapping
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'new': return 'text-primary bg-primary/10 ring-primary/20';
      case 'acknowledged': return 'text-blue-400 bg-blue-400/10 ring-blue-400/20';
      case 'resolved': return 'text-green-400 bg-green-400/10 ring-green-400/20';
      default: return 'text-gray-400 bg-gray-400/10 ring-gray-400/20';
    }
  };

  // Severity icon mapping
  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'critical': return 'error';
      case 'high': return 'warning';
      case 'medium': return 'info';
      case 'low': return 'check_circle';
      default: return 'help';
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-white tracking-tight text-[28px] font-bold leading-tight font-display">
            Anomaly Detection & Alerts
          </h1>
          <p className="text-text-muted text-sm font-normal mt-1">
            Monitor system anomalies detected by AI-powered analysis and baseline comparisons.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="flex items-center gap-2 rounded-lg bg-panel-dark hover:bg-border-dark/50 border border-border-dark text-white px-4 py-2 transition-colors font-medium text-sm cursor-pointer">
            <span className="material-symbols-outlined text-[18px]">tune</span>
            Configure Alerts
          </button>
          <button className="flex items-center gap-2 rounded-lg bg-primary hover:bg-primary/90 text-background-dark px-4 py-2 transition-colors font-bold text-sm cursor-pointer">
            <span className="material-symbols-outlined text-[18px]">refresh</span>
            Refresh
          </button>
        </div>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-xl border border-border-dark bg-panel-dark p-5 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm font-medium text-text-muted uppercase tracking-wider">
              Total Anomalies
            </p>
            <span className="material-symbols-outlined text-primary text-[20px]">
              warning
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-white font-display">
              {anomalies.length}
            </span>
            <span className="text-xs text-text-muted">detected</span>
          </div>
        </div>

        <div className="rounded-xl border border-red-400/30 bg-panel-dark p-5 shadow-[0_0_15px_rgba(248,113,113,0.05)]">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm font-medium text-red-400 uppercase tracking-wider">
              Critical + High
            </p>
            <span className="material-symbols-outlined text-red-400 text-[20px]">
              error
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-white font-display">
              {criticalCount + highCount}
            </span>
            <span className="text-xs text-red-400">require attention</span>
          </div>
        </div>

        <div className="rounded-xl border border-primary/30 bg-panel-light p-5 shadow-[0_0_15px_rgba(250,204,21,0.05)]">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm font-medium text-primary uppercase tracking-wider">
              New / Unresolved
            </p>
            <span className="material-symbols-outlined text-primary text-[20px] animate-pulse">
              notifications_active
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-white font-display">
              {newCount}
            </span>
            <span className="text-xs text-primary">needs review</span>
          </div>
        </div>

        <div className="rounded-xl border border-border-dark bg-panel-dark p-5 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm font-medium text-text-muted uppercase tracking-wider">
              Avg Confidence
            </p>
            <span className="material-symbols-outlined text-green-400 text-[20px]">
              speed
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-white font-display">
              {avgConfidence.toFixed(0)}%
            </span>
            <span className="text-xs text-text-muted">accuracy</span>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="rounded-xl border border-border-dark bg-panel-dark p-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-text-muted text-[18px]">filter_alt</span>
            <span className="text-sm font-medium text-white">Filters:</span>
          </div>

          {/* Severity Filter */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-text-muted uppercase tracking-wider">Severity</label>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="bg-background-dark border border-border-dark rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 cursor-pointer"
            >
              <option value="all">All</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-text-muted uppercase tracking-wider">Status</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-background-dark border border-border-dark rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 cursor-pointer"
            >
              <option value="all">All</option>
              <option value="new">New</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>

          {/* Service Filter */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-text-muted uppercase tracking-wider">Service</label>
            <select
              value={serviceFilter}
              onChange={(e) => setServiceFilter(e.target.value)}
              className="bg-background-dark border border-border-dark rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 cursor-pointer"
            >
              <option value="all">All Services</option>
              {uniqueServices.map((service) => (
                <option key={service} value={service}>
                  {service}
                </option>
              ))}
            </select>
          </div>

          {/* Clear Filters */}
          {(severityFilter !== 'all' || statusFilter !== 'all' || serviceFilter !== 'all') && (
            <button
              onClick={() => {
                setSeverityFilter('all');
                setStatusFilter('all');
                setServiceFilter('all');
              }}
              className="ml-auto text-xs text-primary hover:text-white font-medium transition-colors cursor-pointer"
            >
              Clear Filters
            </button>
          )}
        </div>
      </div>

      {/* Anomalies List */}
      <div className="rounded-xl border border-border-dark bg-panel-dark overflow-hidden">
        <div className="flex items-center justify-between border-b border-border-dark px-6 py-4">
          <h3 className="text-lg font-bold text-white">
            Detected Anomalies {anomalies.length > 0 && `(${anomalies.length})`}
          </h3>
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span className="material-symbols-outlined text-[16px]">schedule</span>
            <span>Auto-refresh: 30s</span>
          </div>
        </div>

        {isLoading ? (
          <div className="p-12 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : anomalies.length === 0 ? (
          <div className="p-12 text-center text-text-muted">
            <span className="material-symbols-outlined text-[64px] mb-4 text-green-400">check_circle</span>
            <p className="text-lg font-medium text-white mb-1">No Anomalies Detected</p>
            <p className="text-sm">Your system is running smoothly with no detected anomalies.</p>
          </div>
        ) : (
          <div className="divide-y divide-border-dark">
            {anomalies.map((anomaly) => (
              <AnomalyCard
                key={anomaly.alert_id}
                anomaly={anomaly}
                getSeverityColor={getSeverityColor}
                getStatusColor={getStatusColor}
                getSeverityIcon={getSeverityIcon}
                onAcknowledge={() => acknowledgeMutation.mutate(anomaly.alert_id)}
                onResolve={() => resolveMutation.mutate(anomaly.alert_id)}
                onInvestigate={() => handleInvestigate(anomaly)}
                isAcknowledging={acknowledgingId === anomaly.alert_id}
                isResolving={resolvingId === anomaly.alert_id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// Anomaly Card Component
interface AnomalyCardProps {
  anomaly: Anomaly;
  getSeverityColor: (severity: string) => string;
  getStatusColor: (status: string) => string;
  getSeverityIcon: (severity: string) => string;
  onAcknowledge: () => void;
  onResolve: () => void;
  onInvestigate: () => void;
  isAcknowledging: boolean;
  isResolving: boolean;
}

const AnomalyCard: React.FC<AnomalyCardProps> = ({
  anomaly,
  getSeverityColor,
  getStatusColor,
  getSeverityIcon,
  onAcknowledge,
  onResolve,
  onInvestigate,
  isAcknowledging,
  isResolving,
}) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="px-6 py-5 hover:bg-border-dark/30 transition-colors">
      <div className="flex items-start gap-4">
        {/* Severity Icon */}
        <div className={`size-10 rounded-lg flex items-center justify-center ${
          anomaly.severity === 'critical' ? 'bg-red-400/10 text-red-400' :
          anomaly.severity === 'high' ? 'bg-orange-400/10 text-orange-400' :
          anomaly.severity === 'medium' ? 'bg-yellow-400/10 text-yellow-400' :
          'bg-blue-400/10 text-blue-400'
        }`}>
          <span className="material-symbols-outlined text-[20px]">
            {getSeverityIcon(anomaly.severity)}
          </span>
        </div>

        {/* Main Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-4 mb-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <h4 className="text-white font-bold text-base truncate">
                  {anomaly.anomaly_type.replace(/_/g, ' ').toUpperCase()}
                </h4>
                <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-bold uppercase ring-1 ring-inset ${getSeverityColor(anomaly.severity)}`}>
                  {anomaly.severity}
                </span>
                <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-bold uppercase ring-1 ring-inset ${getStatusColor(anomaly.status)}`}>
                  {anomaly.status}
                </span>
              </div>
              <p className="text-sm text-gray-200 mb-2">{anomaly.description}</p>
              <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted">
                <span className="flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">dns</span>
                  {anomaly.service}
                </span>
                <span className="flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">cloud</span>
                  {anomaly.environment}
                </span>
                <span className="flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">schedule</span>
                  {format(new Date(anomaly.detected_at), 'MMM d, yyyy HH:mm')}
                </span>
                <span className="flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">speed</span>
                  {(anomaly.confidence_score * 100).toFixed(0)}% confidence
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => setExpanded(!expanded)}
                className="text-primary hover:text-white transition-colors cursor-pointer"
                title={expanded ? 'Collapse' : 'Expand'}
              >
                <span className="material-symbols-outlined text-[20px]">
                  {expanded ? 'expand_less' : 'expand_more'}
                </span>
              </button>
              {anomaly.status === 'new' && (
                <button
                  onClick={onAcknowledge}
                  disabled={isAcknowledging}
                  className="px-3 py-1.5 rounded-lg bg-blue-400/10 hover:bg-blue-400/20 text-blue-400 text-xs font-bold transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1 cursor-pointer"
                  title="Acknowledge"
                >
                  {isAcknowledging && (
                    <span className="material-symbols-outlined text-[14px] animate-spin">progress_activity</span>
                  )}
                  Acknowledge
                </button>
              )}
              {anomaly.status !== 'resolved' && (
                <button
                  onClick={onResolve}
                  disabled={isResolving}
                  className="px-3 py-1.5 rounded-lg bg-green-400/10 hover:bg-green-400/20 text-green-400 text-xs font-bold transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1 cursor-pointer"
                  title="Mark as Resolved"
                >
                  {isResolving && (
                    <span className="material-symbols-outlined text-[14px] animate-spin">progress_activity</span>
                  )}
                  Resolve
                </button>
              )}
              <button
                onClick={onInvestigate}
                className="px-3 py-1.5 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary text-xs font-bold transition-colors flex items-center gap-1 cursor-pointer"
                title="Investigate in Semantic Search"
              >
                <span className="material-symbols-outlined text-[14px]">search</span>
                Investigate
              </button>
            </div>
          </div>

          {/* Expanded Details */}
          {expanded && anomaly.metrics && (
            <div className="mt-4 p-4 rounded-lg bg-black/20 border border-border-dark">
              <h5 className="text-xs font-bold text-primary uppercase tracking-wider mb-3">
                Anomaly Metrics
              </h5>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(anomaly.metrics).map(([key, value]) => (
                  <div key={key} className="bg-background-dark/50 rounded-lg p-3">
                    <p className="text-xs text-text-muted mb-1">
                      {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </p>
                    <p className="text-white font-mono font-bold">
                      {typeof value === 'number' ? value.toLocaleString() : value}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
