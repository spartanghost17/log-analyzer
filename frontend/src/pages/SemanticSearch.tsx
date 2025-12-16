import React, { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import toast from "react-hot-toast";
import { api, type SemanticSearchResult } from "../api/client";
import { mockApi } from "../api/mock";
import { format } from "date-fns";

// Toggle this to switch between mock and real API
const USE_MOCK_API = true;

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
                            <span className="text-primary/80">"{format(new Date(result.timestamp), 'yyyy-MM-dd HH:mm')}"</span>
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

                  <button className="w-full bg-primary hover:bg-primary-hover text-black font-semibold text-sm py-2.5 rounded-lg transition flex items-center justify-center gap-2 group-hover:scale-[1.02] active:scale-100 cursor-pointer">
                    <span className="material-icons-outlined text-lg">psychology</span>
                    Analyze with LLM
                  </button>
                </div>
              );
            })}
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
