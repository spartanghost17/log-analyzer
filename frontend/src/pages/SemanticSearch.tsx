import React, { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import toast from "react-hot-toast";
import { api, type SemanticSearchResult } from "../api/client";
import { mockApi } from "../api/mock";
import { format } from "date-fns";

// Toggle this to switch between mock and real API
const USE_MOCK_API = false;

export const SemanticSearch = () => {
  const location = useLocation();
  const locationState = location.state as any;

  // Initialize state from navigation or defaults
  const [searchQuery, setSearchQuery] = useState(
    locationState?.initialQuery || ""
  );
  const [selectedResult, setSelectedResult] =
    useState<SemanticSearchResult | null>(null);
  const [filters, setFilters] = useState({
    level: locationState?.initialFilters?.level || "",
    service: locationState?.initialFilters?.service || "",
    timeRange: locationState?.initialFilters?.timeRange || "1h",
  });
  const [selectedCluster, setSelectedCluster] = useState<{
    key: string;
    results: SemanticSearchResult[];
    avgSimilarity: number;
  } | null>(null);
  const [expandedLogIndex, setExpandedLogIndex] = useState<number | null>(null);

  // Auto-trigger search if coming from anomaly investigation
  useEffect(() => {
    if (locationState?.fromAnomaly && locationState?.initialQuery) {
      // Trigger search automatically with a small delay
      const timer = setTimeout(() => {
        handleSearch();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [locationState?.fromAnomaly]);

  const searchMutation = useMutation({
    mutationFn: (query: string) =>
      USE_MOCK_API
        ? mockApi.searchSemantic({
            query,
            top_k: 20,
            level: filters.level,
            service: filters.service || undefined,
          })
        : api.searchSemantic({
            query,
            top_k: 20,
            level: filters.level,
            service: filters.service || undefined,
          }),
  });

  const handleSearch = () => {
    if (searchQuery.trim()) {
      searchMutation.mutate(searchQuery);
      // Set first result as selected
      if (searchMutation.data?.results?.length) {
        setSelectedResult(searchMutation.data.results[0]);
      }
    }
  };

  // Get all results from API
  const allResults = searchMutation.data?.results || [];

  // Filter results client-side based on selected level
  const results = allResults.filter((result) => {
    // If no level filter or "All Levels" selected, show all
    if (!filters.level || filters.level === "") return true;
    // Otherwise, filter by matching level
    return result.level === filters.level;
  });

  // Group results by similarity clusters
  const clusters = results.reduce((acc: Record<string, SemanticSearchResult[]>, result) => {
    // Simple clustering based on first few words of message
    const clusterKey = result.message.split(' ').slice(0, 3).join(' ');
    if (!acc[clusterKey]) {
      acc[clusterKey] = [];
    }
    acc[clusterKey].push(result);
    return acc;
  }, {});

  const getSimilarityPercent = (score: number) => Math.round(score * 100);

  return (
    <div className="flex flex-col h-full gap-8">
      {/* Hero Section */}
      <div className="flex flex-col items-center justify-center py-12 md:py-20 relative animate-fade-in-up">
        <div className="mb-8 relative">
          <div className="w-20 h-20 bg-gradient-to-b from-surface-dark to-black rounded-2xl flex items-center justify-center border border-primary/20 shadow-glow-primary">
            <span className="material-icons-outlined text-4xl text-primary animate-pulse">psychology_alt</span>
          </div>
          <span className="absolute -top-1 -right-1 flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span>
          </span>
        </div>

        <h2 className="text-2xl md:text-3xl font-display font-semibold text-center mb-8 dark:text-white">
          What would you like to investigate today?
        </h2>

        <div className="w-full max-w-3xl relative group">
          <div className="absolute inset-0 bg-gradient-to-r from-primary/20 via-primary/10 to-primary/20 rounded-xl blur opacity-75 group-hover:opacity-100 transition duration-500"></div>
          <div className="relative bg-surface-light dark:bg-[#15161C] rounded-xl border border-gray-200 dark:border-primary/30 shadow-2xl flex items-center p-1">
            <span className="pl-4 material-icons-outlined text-primary">auto_awesome</span>
            <input
              className="w-full bg-transparent border-none focus:ring-0 focus:outline-none text-lg py-4 px-4 dark:text-white placeholder-gray-400 dark:placeholder-gray-500"
              placeholder="Ask Synaps: Find logs similar to trace ID 123..."
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && handleSearch()}
            />
            <button
              onClick={handleSearch}
              disabled={searchMutation.isPending}
              className="hidden md:flex items-center gap-2 bg-primary hover:bg-primary-hover text-black font-medium px-6 py-2.5 rounded-lg mr-1 transition-transform active:scale-95 shadow-lg shadow-primary/20 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              <span>Analyze</span>
              <span className="material-icons-outlined text-sm">arrow_forward</span>
            </button>
          </div>
          <div className="absolute -bottom-8 left-0 right-0 flex justify-center gap-4 text-xs text-gray-500 dark:text-gray-400">
            <span className="cursor-pointer hover:text-primary transition">Try: "Authentication failures last hour"</span>
            <span className="hidden sm:inline">•</span>
            <span className="cursor-pointer hover:text-primary transition">Try: "Latency spikes in checkout service"</span>
          </div>
        </div>
      </div>

      {/* Results Section */}
      {searchMutation.isPending && (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
        </div>
      )}

      {!searchMutation.isPending && Object.keys(clusters).length > 0 && (
        <div className="flex-1 animate-fade-in-up" style={{ animationDelay: '150ms' }}>
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white flex items-center gap-2">
              <span className="material-icons-outlined text-primary">bubble_chart</span>
              Semantic Clusters
            </h3>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">Analysis timeframe:</span>
              <select
                value={filters.timeRange}
                onChange={(e) => setFilters({ ...filters, timeRange: e.target.value })}
                className="bg-transparent border border-gray-300 dark:border-gray-700 rounded text-sm text-gray-700 dark:text-gray-300 px-3 py-1 focus:ring-primary focus:border-primary"
              >
                <option value="1h">Last 1 Hour</option>
                <option value="24h">Last 24 Hours</option>
                <option value="7d">Last 7 Days</option>
              </select>
            </div>
          </div>

          <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 -mt-4">
            Synaps has detected patterns in your logs and grouped them by semantic similarity.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {Object.entries(clusters).slice(0, 3).map(([clusterKey, clusterResults], idx) => {
              const avgSimilarity = clusterResults.reduce((sum, r) => sum + r.similarity_score, 0) / clusterResults.length;
              const dominantLevel = clusterResults[0]?.level || 'ERROR';
              const dominantService = clusterResults[0]?.service || 'unknown';
              const clusterColors = ['red', 'orange', 'yellow'];
              const color = clusterColors[idx % 3];

              return (
                <div
                  key={clusterKey}
                  className="group bg-white dark:bg-surface-dark border border-gray-200 dark:border-border-dark rounded-xl p-5 hover:border-primary/50 dark:hover:border-primary/50 transition-all duration-300 hover:shadow-lg hover:shadow-primary/5 flex flex-col h-full"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full bg-${color}-500 ${idx === 0 ? 'animate-pulse' : ''}`}></div>
                      <h4 className="font-medium text-gray-900 dark:text-white text-sm">
                        Cluster: {clusterKey}
                      </h4>
                    </div>
                    <span className="px-2 py-1 rounded bg-surface-light dark:bg-white/5 border border-gray-200 dark:border-white/10 text-xs text-gray-500 dark:text-gray-400 font-mono">
                      {getSimilarityPercent(avgSimilarity)}% Similarity
                    </span>
                  </div>

                  <div className="flex-1 mb-6 relative">
                    <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-gray-200 dark:bg-gray-700 rounded-full"></div>
                    <div className="pl-4 space-y-3">
                      {clusterResults.slice(0, 5).map((result, i) => (
                        <div
                          key={result.log_id}
                          className="text-[11px] font-mono text-gray-600 dark:text-gray-300 leading-relaxed"
                          style={{ opacity: 1 - (i * 0.15) }}
                        >
                          <div className="flex items-start gap-2 flex-wrap">
                            <span className="text-gray-400 dark:text-gray-500 shrink-0">timestamp=</span>
                            <span className="text-primary/80">"{format(new Date(result.timestamp), 'dd-MM-yyyy HH:mm:ss')}"</span>
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold shrink-0 ${
                              result.level === 'ERROR' ? 'bg-red-500/20 text-red-400' :
                              result.level === 'WARN' ? 'bg-yellow-500/20 text-yellow-400' :
                              result.level === 'INFO' ? 'bg-blue-500/20 text-blue-400' :
                              'bg-purple-500/20 text-purple-400'
                            }`}>
                              {result.level}
                            </span>
                          </div>
                          <div className="mt-1 line-clamp-2 text-gray-700 dark:text-gray-300">
                            msg="{result.message.substring(0, 80)}..."
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-white dark:from-surface-dark to-transparent"></div>
                  </div>

                  <button 
                    onClick={() => setSelectedCluster({
                      key: clusterKey,
                      results: clusterResults,
                      avgSimilarity
                    })}
                    className="w-full bg-primary hover:bg-primary-hover text-black font-semibold text-sm py-2.5 rounded-lg transition flex items-center justify-center gap-2 group-hover:scale-[1.02] active:scale-100 cursor-pointer"
                  >
                    <span className="material-icons-outlined text-lg">visibility</span>
                    View Details ({clusterResults.length} logs)
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Cluster Details Modal */}
      {selectedCluster && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white dark:bg-surface-dark rounded-2xl shadow-2xl border border-gray-200 dark:border-border-dark max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col animate-scale-in">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-800">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <span className="material-icons-outlined text-primary">bubble_chart</span>
                </div>
                <div>
                  <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                    Cluster: {selectedCluster.key}
                  </h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {selectedCluster.results.length} logs · {getSimilarityPercent(selectedCluster.avgSimilarity)}% similarity
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setSelectedCluster(null);
                  setExpandedLogIndex(null);
                }}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition cursor-pointer"
              >
                <span className="material-icons-outlined text-gray-500">close</span>
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Cluster Stats */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-gray-50 dark:bg-surface-darker rounded-lg p-4 border border-gray-200 dark:border-gray-800">
                  <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Total Logs</div>
                  <div className="text-2xl font-bold text-gray-900 dark:text-white">{selectedCluster.results.length}</div>
                </div>
                <div className="bg-gray-50 dark:bg-surface-darker rounded-lg p-4 border border-gray-200 dark:border-gray-800">
                  <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Avg Similarity</div>
                  <div className="text-2xl font-bold text-primary">{getSimilarityPercent(selectedCluster.avgSimilarity)}%</div>
                </div>
                <div className="bg-gray-50 dark:bg-surface-darker rounded-lg p-4 border border-gray-200 dark:border-gray-800">
                  <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Services</div>
                  <div className="text-2xl font-bold text-gray-900 dark:text-white">
                    {new Set(selectedCluster.results.map(r => r.service)).size}
                  </div>
                </div>
                <div className="bg-gray-50 dark:bg-surface-darker rounded-lg p-4 border border-gray-200 dark:border-gray-800">
                  <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Severity</div>
                  <div className="flex gap-1 mt-1">
                    {selectedCluster.results.some(r => r.level === 'FATAL') && (
                      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-purple-500/20 text-purple-400">FATAL</span>
                    )}
                    {selectedCluster.results.some(r => r.level === 'ERROR') && (
                      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-red-500/20 text-red-400">ERROR</span>
                    )}
                    {selectedCluster.results.some(r => r.level === 'WARN') && (
                      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-yellow-500/20 text-yellow-400">WARN</span>
                    )}
                  </div>
                </div>
              </div>

              {/* All Logs */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider flex items-center gap-2">
                  <span className="material-icons-outlined text-sm">receipt_long</span>
                  All Logs in Cluster
                </h3>
                {selectedCluster.results.map((result, idx) => {
                  const isExpanded = expandedLogIndex === idx;
                  return (
                    <div
                      key={result.log_id}
                      className={`bg-gray-50 dark:bg-surface-darker rounded-lg p-4 border border-gray-200 dark:border-gray-800 hover:border-primary/50 transition-all ${
                        isExpanded ? 'border-primary/50 shadow-lg' : ''
                      }`}
                    >
                      <div
                        onClick={() => setExpandedLogIndex(isExpanded ? null : idx)}
                        className="cursor-pointer"
                      >
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono text-gray-500 dark:text-gray-400">
                              #{idx + 1}
                            </span>
                            <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                              result.level === 'FATAL' ? 'bg-purple-500/20 text-purple-400' :
                              result.level === 'ERROR' ? 'bg-red-500/20 text-red-400' :
                              result.level === 'WARN' ? 'bg-yellow-500/20 text-yellow-400' :
                              'bg-blue-500/20 text-blue-400'
                            }`}>
                              {result.level}
                            </span>
                            <span className="text-xs text-gray-600 dark:text-gray-400">
                              {result.service}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-primary font-semibold">
                              {getSimilarityPercent(result.similarity_score)}% match
                            </span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                navigator.clipboard.writeText(result.log_id);
                                toast.success('Log ID copied!');
                              }}
                              className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded cursor-pointer transition"
                              title="Copy log ID"
                            >
                              <span className="material-icons-outlined text-xs text-gray-500">content_copy</span>
                            </button>
                            <span className={`material-icons-outlined text-sm text-gray-400 transition-transform ${
                              isExpanded ? 'rotate-180' : ''
                            }`}>
                              expand_more
                            </span>
                          </div>
                        </div>
                        <div className="text-sm text-gray-700 dark:text-gray-300 font-mono mb-2 leading-relaxed">
                          {result.message.length > 150 && !isExpanded 
                            ? result.message.substring(0, 150) + '...' 
                            : result.message}
                        </div>
                        <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                          <span className="flex items-center gap-1">
                            <span className="material-icons-outlined text-xs">schedule</span>
                            {format(new Date(result.timestamp), 'MMM d, HH:mm:ss')}
                          </span>
                          {result.trace_id && (
                            <span className="flex items-center gap-1">
                              <span className="material-icons-outlined text-xs">route</span>
                              Trace: {result.trace_id.substring(0, 8)}...
                            </span>
                          )}
                          {result.user_id && (
                            <span className="flex items-center gap-1">
                              <span className="material-icons-outlined text-xs">person</span>
                              {result.user_id}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Expanded Details */}
                      {isExpanded && (
                        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 space-y-4 animate-fade-in">
                          
                          {/* Logger & Thread Info */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {result.logger_name && (
                              <div className="bg-blue-50 dark:bg-blue-900/10 p-3 rounded border border-blue-200 dark:border-blue-800">
                                <div className="text-xs text-blue-600 dark:text-blue-400 mb-1 flex items-center gap-1">
                                  <span className="material-icons-outlined text-xs">code</span>
                                  Logger Name
                                </div>
                                <div className="text-sm font-mono text-gray-900 dark:text-white">{result.logger_name}</div>
                              </div>
                            )}
                            {result.thread_name && (
                              <div className="bg-blue-50 dark:bg-blue-900/10 p-3 rounded border border-blue-200 dark:border-blue-800">
                                <div className="text-xs text-blue-600 dark:text-blue-400 mb-1 flex items-center gap-1">
                                  <span className="material-icons-outlined text-xs">alt_route</span>
                                  Thread Name
                                </div>
                                <div className="text-sm font-mono text-gray-900 dark:text-white">{result.thread_name}</div>
                              </div>
                            )}
                          </div>

                          {/* Stack Trace */}
                          {result.stack_trace && (
                            <div>
                              <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-2 flex items-center gap-1">
                                <span className="material-icons-outlined text-xs text-red-500">bug_report</span>
                                Stack Trace
                              </h4>
                              <pre className="text-xs font-mono text-red-900 dark:text-red-300 bg-red-50 dark:bg-red-900/10 p-3 rounded border border-red-200 dark:border-red-800 overflow-x-auto max-h-64">
                                {result.stack_trace}
                              </pre>
                            </div>
                          )}

                          {/* Distributed Tracing */}
                          <div>
                            <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-2 flex items-center gap-1">
                              <span className="material-icons-outlined text-xs text-purple-500">timeline</span>
                              Distributed Tracing
                            </h4>
                            <div className="grid grid-cols-1 gap-2">
                              {result.trace_id && (
                                <div className="flex items-center justify-between bg-purple-50 dark:bg-purple-900/10 p-2 rounded border border-purple-200 dark:border-purple-800">
                                  <span className="text-xs text-purple-600 dark:text-purple-400 font-medium">Trace ID</span>
                                  <span className="text-xs font-mono text-gray-900 dark:text-white">{result.trace_id}</span>
                                </div>
                              )}
                              {result.span_id && (
                                <div className="flex items-center justify-between bg-purple-50 dark:bg-purple-900/10 p-2 rounded border border-purple-200 dark:border-purple-800">
                                  <span className="text-xs text-purple-600 dark:text-purple-400 font-medium">Span ID</span>
                                  <span className="text-xs font-mono text-gray-900 dark:text-white">{result.span_id}</span>
                                </div>
                              )}
                              {result.parent_span_id && (
                                <div className="flex items-center justify-between bg-purple-50 dark:bg-purple-900/10 p-2 rounded border border-purple-200 dark:border-purple-800">
                                  <span className="text-xs text-purple-600 dark:text-purple-400 font-medium">Parent Span ID</span>
                                  <span className="text-xs font-mono text-gray-900 dark:text-white">{result.parent_span_id}</span>
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Infrastructure Details */}
                          <div>
                            <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-2 flex items-center gap-1">
                              <span className="material-icons-outlined text-xs text-cyan-500">dns</span>
                              Infrastructure
                            </h4>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                              {result.host && (
                                <div className="bg-cyan-50 dark:bg-cyan-900/10 p-3 rounded border border-cyan-200 dark:border-cyan-800">
                                  <div className="text-xs text-cyan-600 dark:text-cyan-400 mb-1">Host</div>
                                  <div className="text-sm font-mono text-gray-900 dark:text-white truncate" title={result.host}>{result.host}</div>
                                </div>
                              )}
                              {result.pod_name && (
                                <div className="bg-cyan-50 dark:bg-cyan-900/10 p-3 rounded border border-cyan-200 dark:border-cyan-800">
                                  <div className="text-xs text-cyan-600 dark:text-cyan-400 mb-1">Pod</div>
                                  <div className="text-sm font-mono text-gray-900 dark:text-white truncate" title={result.pod_name}>{result.pod_name}</div>
                                </div>
                              )}
                              {result.container_id && (
                                <div className="bg-cyan-50 dark:bg-cyan-900/10 p-3 rounded border border-cyan-200 dark:border-cyan-800">
                                  <div className="text-xs text-cyan-600 dark:text-cyan-400 mb-1">Container</div>
                                  <div className="text-sm font-mono text-gray-900 dark:text-white">{result.container_id.substring(0, 12)}</div>
                                </div>
                              )}
                              {result.environment && (
                                <div className="bg-cyan-50 dark:bg-cyan-900/10 p-3 rounded border border-cyan-200 dark:border-cyan-800">
                                  <div className="text-xs text-cyan-600 dark:text-cyan-400 mb-1">Environment</div>
                                  <div className="text-sm font-semibold text-gray-900 dark:text-white">{result.environment}</div>
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Labels */}
                          {result.labels && Object.keys(result.labels).length > 0 && (
                            <div>
                              <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-2 flex items-center gap-1">
                                <span className="material-icons-outlined text-xs text-green-500">label</span>
                                Labels
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                {Object.entries(result.labels).map(([key, value]) => {
                                  const valueStr = String(value);
                                  return (
                                    <div key={key} className="bg-green-50 dark:bg-green-900/10 p-2 rounded border border-green-200 dark:border-green-800">
                                      <div className="text-xs text-green-600 dark:text-green-400 font-medium">{key}</div>
                                      <div className="text-xs font-mono text-gray-900 dark:text-white truncate" title={valueStr}>{valueStr}</div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* HTTP Metadata */}
                          {result.metadata && (
                            <div>
                              <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-2 flex items-center gap-1">
                                <span className="material-icons-outlined text-xs text-orange-500">http</span>
                                HTTP & Request Metadata
                              </h4>
                              <div className="bg-orange-50 dark:bg-orange-900/10 p-3 rounded border border-orange-200 dark:border-orange-800">
                                <pre className="text-xs font-mono text-gray-700 dark:text-gray-300 overflow-x-auto">
                                  {(() => {
                                    try {
                                      const parsed = typeof result.metadata === 'string' 
                                        ? JSON.parse(result.metadata) 
                                        : result.metadata;
                                      return JSON.stringify(parsed, null, 2);
                                    } catch (e) {
                                      return result.metadata;
                                    }
                                  })()}
                                </pre>
                              </div>
                            </div>
                          )}

                          {/* Correlation IDs */}
                          <div>
                            <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-2 flex items-center gap-1">
                              <span className="material-icons-outlined text-xs text-indigo-500">fingerprint</span>
                              Correlation IDs
                            </h4>
                            <div className="grid grid-cols-1 gap-2">
                              <div className="flex items-center justify-between bg-indigo-50 dark:bg-indigo-900/10 p-2 rounded border border-indigo-200 dark:border-indigo-800">
                                <span className="text-xs text-indigo-600 dark:text-indigo-400 font-medium">Log ID</span>
                                <span className="text-xs font-mono text-gray-900 dark:text-white">{result.log_id}</span>
                              </div>
                              {result.request_id && (
                                <div className="flex items-center justify-between bg-indigo-50 dark:bg-indigo-900/10 p-2 rounded border border-indigo-200 dark:border-indigo-800">
                                  <span className="text-xs text-indigo-600 dark:text-indigo-400 font-medium">Request ID</span>
                                  <span className="text-xs font-mono text-gray-900 dark:text-white">{result.request_id}</span>
                                </div>
                              )}
                              {result.correlation_id && (
                                <div className="flex items-center justify-between bg-indigo-50 dark:bg-indigo-900/10 p-2 rounded border border-indigo-200 dark:border-indigo-800">
                                  <span className="text-xs text-indigo-600 dark:text-indigo-400 font-medium">Correlation ID</span>
                                  <span className="text-xs font-mono text-gray-900 dark:text-white">{result.correlation_id}</span>
                                </div>
                              )}
                              {result.user_id && (
                                <div className="flex items-center justify-between bg-indigo-50 dark:bg-indigo-900/10 p-2 rounded border border-indigo-200 dark:border-indigo-800">
                                  <span className="text-xs text-indigo-600 dark:text-indigo-400 font-medium">User ID</span>
                                  <span className="text-xs font-mono text-gray-900 dark:text-white">{result.user_id}</span>
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Source Code Location */}
                          {(result.source_file || result.source_type) && (
                            <div>
                              <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-2 flex items-center gap-1">
                                <span className="material-icons-outlined text-xs text-pink-500">source</span>
                                Source Information
                              </h4>
                              <div className="space-y-2">
                                {result.source_type && (
                                  <div className="bg-pink-50 dark:bg-pink-900/10 p-2 rounded border border-pink-200 dark:border-pink-800">
                                    <div className="text-xs text-pink-600 dark:text-pink-400 mb-1">Source Type</div>
                                    <div className="text-sm font-semibold text-gray-900 dark:text-white">{result.source_type}</div>
                                  </div>
                                )}
                                {result.source_file && (
                                  <div className="bg-pink-50 dark:bg-pink-900/10 p-2 rounded border border-pink-200 dark:border-pink-800">
                                    <div className="text-xs text-pink-600 dark:text-pink-400 mb-1">File Location</div>
                                    <div className="text-sm font-mono text-gray-900 dark:text-white">
                                      {result.source_file}{result.source_line ? `:${result.source_line}` : ''}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Processing & Anomaly Info */}
                          <div>
                            <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-2 flex items-center gap-1">
                              <span className="material-icons-outlined text-xs text-amber-500">settings</span>
                              Processing Status
                            </h4>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                              <div className="bg-amber-50 dark:bg-amber-900/10 p-3 rounded border border-amber-200 dark:border-amber-800">
                                <div className="text-xs text-amber-600 dark:text-amber-400 mb-1">Vectorized</div>
                                <div className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-1">
                                  {result.is_vectorized ? (
                                    <>
                                      <span className="material-icons-outlined text-green-500 text-sm">check_circle</span>
                                      Yes
                                    </>
                                  ) : (
                                    <>
                                      <span className="material-icons-outlined text-gray-400 text-sm">cancel</span>
                                      No
                                    </>
                                  )}
                                </div>
                              </div>
                              <div className="bg-amber-50 dark:bg-amber-900/10 p-3 rounded border border-amber-200 dark:border-amber-800">
                                <div className="text-xs text-amber-600 dark:text-amber-400 mb-1">Anomaly</div>
                                <div className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-1">
                                  {result.is_anomaly ? (
                                    <>
                                      <span className="material-icons-outlined text-red-500 text-sm">warning</span>
                                      Yes
                                    </>
                                  ) : (
                                    <>
                                      <span className="material-icons-outlined text-green-500 text-sm">check_circle</span>
                                      No
                                    </>
                                  )}
                                </div>
                              </div>
                              {result.anomaly_score !== undefined && result.anomaly_score > 0 && (
                                <div className="bg-amber-50 dark:bg-amber-900/10 p-3 rounded border border-amber-200 dark:border-amber-800">
                                  <div className="text-xs text-amber-600 dark:text-amber-400 mb-1">Anomaly Score</div>
                                  <div className="text-sm font-semibold text-gray-900 dark:text-white">
                                    {result.anomaly_score.toFixed(2)}
                                  </div>
                                </div>
                              )}
                              <div className="bg-amber-50 dark:bg-amber-900/10 p-3 rounded border border-amber-200 dark:border-amber-800">
                                <div className="text-xs text-amber-600 dark:text-amber-400 mb-1">Similarity</div>
                                <div className="text-sm font-semibold text-primary">
                                  {getSimilarityPercent(result.similarity_score)}%
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Timestamps */}
                          <div>
                            <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-2 flex items-center gap-1">
                              <span className="material-icons-outlined text-xs text-gray-500">schedule</span>
                              Timestamps
                            </h4>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                              <div className="bg-gray-100 dark:bg-gray-800 p-3 rounded border border-gray-200 dark:border-gray-700">
                                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Log Timestamp</div>
                                <div className="text-sm font-mono text-gray-900 dark:text-white">
                                  {format(new Date(result.timestamp), 'MMM d, yyyy HH:mm:ss')}
                                </div>
                              </div>
                              {result.ingested_at && (
                                <div className="bg-gray-100 dark:bg-gray-800 p-3 rounded border border-gray-200 dark:border-gray-700">
                                  <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Ingested At</div>
                                  <div className="text-sm font-mono text-gray-900 dark:text-white">
                                    {format(new Date(result.ingested_at), 'MMM d, yyyy HH:mm:ss')}
                                  </div>
                                </div>
                              )}
                              {result.processed_at && (
                                <div className="bg-gray-100 dark:bg-gray-800 p-3 rounded border border-gray-200 dark:border-gray-700">
                                  <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Processed At</div>
                                  <div className="text-sm font-mono text-gray-900 dark:text-white">
                                    {format(new Date(result.processed_at), 'MMM d, yyyy HH:mm:ss')}
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>

                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Common Patterns */}
              <div className="bg-primary/5 border border-primary/20 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider flex items-center gap-2 mb-3">
                  <span className="material-icons-outlined text-primary text-sm">analytics</span>
                  Pattern Analysis
                </h3>
                <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                  <p>• Most common service: <span className="font-semibold text-gray-900 dark:text-white">
                    {(() => {
                      const serviceCounts = selectedCluster.results.reduce((acc, r) => {
                        acc[r.service] = (acc[r.service] || 0) + 1;
                        return acc;
                      }, {} as Record<string, number>);
                      return Object.entries(serviceCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || 'N/A';
                    })()}
                  </span></p>
                  <p>• Time span: <span className="font-semibold text-gray-900 dark:text-white">
                    {(() => {
                      const timestamps = selectedCluster.results.map(r => new Date(r.timestamp).getTime());
                      const range = Math.max(...timestamps) - Math.min(...timestamps);
                      const minutes = Math.floor(range / 60000);
                      return minutes > 0 ? `${minutes} minutes` : 'Less than a minute';
                    })()}
                  </span></p>
                  <p>• Unique traces: <span className="font-semibold text-gray-900 dark:text-white">
                    {new Set(selectedCluster.results.filter(r => r.trace_id).map(r => r.trace_id)).size}
                  </span></p>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between p-6 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-surface-darker">
              <div className="text-xs text-gray-500">
                Cluster discovered by semantic similarity analysis
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    const logIds = selectedCluster.results.map(r => r.log_id).join('\n');
                    navigator.clipboard.writeText(logIds);
                    toast.success('All log IDs copied!');
                  }}
                  className="px-4 py-2 bg-gray-200 dark:bg-gray-800 hover:bg-gray-300 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg transition flex items-center gap-2 cursor-pointer"
                >
                  <span className="material-icons-outlined text-sm">content_copy</span>
                  Export IDs
                </button>
                <button
                  onClick={() => {
                    setSelectedCluster(null);
                    setExpandedLogIndex(null);
                  }}
                  className="px-4 py-2 bg-primary hover:bg-primary-hover text-black rounded-lg transition cursor-pointer"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Recent Investigations */}
      {!searchMutation.isPending && results.length > 0 && (
        <div className="border-t border-gray-200 dark:border-border-dark pt-8 pb-12 mt-4 animate-fade-in-up" style={{ animationDelay: '300ms' }}>
          <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
            Recent Investigations
          </h3>
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5 cursor-pointer transition group">
              <div className="flex items-center gap-3">
                <span className="material-icons-outlined text-gray-400 group-hover:text-primary transition">history</span>
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  Why did the payment service latency spike at 10:00 AM?
                </span>
              </div>
              <span className="text-xs text-gray-400">2 hours ago</span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5 cursor-pointer transition group">
              <div className="flex items-center gap-3">
                <span className="material-icons-outlined text-gray-400 group-hover:text-primary transition">history</span>
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  Find all logs related to user_id: 8842 with status 500
                </span>
              </div>
              <span className="text-xs text-gray-400">Yesterday</span>
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!searchMutation.isPending && !searchMutation.data && (
        <div className="text-center py-20 text-gray-500 dark:text-gray-400 animate-fade-in-up">
          <span className="material-icons-outlined text-[64px] mb-4 opacity-50">search</span>
          <p>Enter a query above to start your investigation</p>
        </div>
      )}
    </div>
  );
};
