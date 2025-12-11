import React, { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, type SemanticSearchResult } from "../api/client";
import { mockApi } from "../api/mock";
import { format } from "date-fns";

// Toggle this to switch between mock and real API
const USE_MOCK_API = true;

export const SemanticSearch = () => {
  const [searchQuery, setSearchQuery] = useState(
    "Show me authentication failures related to the payment gateway timeout"
  );
  const [selectedResult, setSelectedResult] =
    useState<SemanticSearchResult | null>(null);
  const [filters, setFilters] = useState({
    level: "ERROR",
    service: "",
    timeRange: "1h",
    patternGrouping: true,
  });

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

  const results = searchMutation.data?.results || [];

  // Auto-select first result when results change
  React.useEffect(() => {
    if (results.length > 0 && !selectedResult) {
      setSelectedResult(results[0]);
    }
  }, [results, selectedResult]);

  const getSimilarityColor = (score: number) => {
    if (score >= 0.95) return "bg-primary/20 text-primary";
    if (score >= 0.85) return "bg-[#494922] text-text-muted";
    return "bg-border-dark text-text-muted";
  };

  const getLevelBadgeColor = (level: string) => {
    switch (level) {
      case "ERROR":
        return "text-red-400 border-red-900/50 bg-red-900/20";
      case "WARN":
        return "text-orange-400 border-orange-900/50 bg-orange-900/20";
      case "INFO":
        return "text-blue-400 border-blue-900/50 bg-blue-900/20";
      default:
        return "text-gray-400 border-gray-900/50 bg-gray-900/20";
    }
  };

  return (
    <div className="flex flex-col h-full -m-6 md:-m-8 bg-[#232310]">
      {/* Search & Header Section */}
      <div className="shrink-0 px-6 pt-6 pb-2 border-b border-border-dark/50 bg-[#232310] z-10">
        <div className="mx-auto w-full max-w-[1600px] flex flex-col gap-4">
          {/* Page Heading */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
              <h1 className="text-white tracking-tight text-[28px] font-bold leading-tight font-display">
                Semantic Search & Analysis
              </h1>
              <p className="text-text-muted text-sm font-normal mt-1">
                Investigate logs using natural language queries and AI-driven
                insights.
              </p>
            </div>
            <div className="flex items-center gap-3 rounded-lg border border-[#686831] bg-[#2a2a15] px-4 py-2">
              <span className="material-symbols-outlined text-primary">
                auto_awesome
              </span>
              <div className="flex flex-col">
                <span className="text-white text-xs font-bold">
                  AI-Powered Search
                </span>
                <span className="text-text-muted text-xs">
                  Using Jina Embeddings v3
                </span>
              </div>
            </div>
          </div>

          {/* Search Bar */}
          <div className="w-full mt-2">
            <div className="flex flex-col h-12 w-full group">
              <div className="flex w-full flex-1 items-center rounded-xl bg-[#2a2a15] border border-border-dark focus-within:border-primary/50 transition-colors shadow-lg shadow-black/20">
                <div className="text-text-muted flex items-center justify-center pl-4 pr-2">
                  <span className="material-symbols-outlined">
                    auto_awesome
                  </span>
                </div>
                <input
                  className="flex w-full min-w-0 flex-1 bg-transparent text-white focus:outline-none placeholder:text-text-muted/70 px-2 text-base font-normal h-full font-display"
                  placeholder="Describe the issue (e.g., 'Why did the checkout service fail at 2 AM?')..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyPress={(e) => e.key === "Enter" && handleSearch()}
                />
                <div className="pr-2">
                  <button
                    onClick={handleSearch}
                    disabled={searchMutation.isPending}
                    className="p-2 text-text-muted hover:text-white transition-colors rounded-lg disabled:opacity-50"
                  >
                    <span className="material-symbols-outlined">search</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Chips / Filters */}
          <div className="flex gap-2 overflow-x-auto pb-2">
            <select
              value={filters.level}
              onChange={(e) =>
                setFilters({ ...filters, level: e.target.value })
              }
              className="flex h-8 shrink-0 items-center gap-x-2 rounded-lg bg-[#2a2a15] border border-border-dark hover:border-[#686831] px-3 transition-colors text-white text-xs font-medium"
            >
              <option value="">All Levels</option>
              <option value="ERROR">Level: Error</option>
              <option value="WARN">Level: Warn</option>
              <option value="INFO">Level: Info</option>
            </select>

            <button
              onClick={() =>
                setFilters({
                  ...filters,
                  patternGrouping: !filters.patternGrouping,
                })
              }
              className={`flex h-8 shrink-0 items-center gap-x-2 rounded-lg bg-[#2a2a15] border px-3 transition-colors ${
                filters.patternGrouping
                  ? "border-primary/40"
                  : "border-border-dark hover:border-[#686831]"
              }`}
            >
              <span
                className={`text-xs font-bold ${
                  filters.patternGrouping ? "text-primary" : "text-white"
                }`}
              >
                Pattern Grouping: {filters.patternGrouping ? "On" : "Off"}
              </span>
              {filters.patternGrouping && (
                <span className="material-symbols-outlined text-primary text-[16px]">
                  check
                </span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Split Pane Content */}
      <div className="flex flex-1 overflow-hidden w-full max-w-[1600px] mx-auto">
        {/* LEFT PANEL: Results List */}
        <div className="w-full lg:w-5/12 xl:w-4/12 flex flex-col border-r border-border-dark/50 bg-[#232310] overflow-hidden">
          <div className="flex items-center justify-between px-6 py-3 border-b border-border-dark/30">
            <span className="text-xs font-bold uppercase tracking-wider text-text-muted">
              Results ({results.length})
            </span>
            <span className="text-xs text-text-muted flex items-center gap-1">
              Sorted by:{" "}
              <span className="text-white font-medium">Similarity</span>
            </span>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {searchMutation.isPending && (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
              </div>
            )}

            {searchMutation.isError && (
              <div className="text-center py-12 text-red-400">
                <span className="material-symbols-outlined text-[48px] mb-2">
                  error
                </span>
                <p>Failed to search logs</p>
              </div>
            )}

            {!searchMutation.isPending && results.length === 0 && (
              <div className="text-center py-12 text-text-muted">
                <span className="material-symbols-outlined text-[48px] mb-2">
                  search
                </span>
                <p>Enter a query to search</p>
              </div>
            )}

            {results.map((result, index) => {
              const isSelected = selectedResult?.log_id === result.log_id;
              const similarityPercent = Math.round(
                result.similarity_score * 100
              );

              return (
                <div
                  key={result.log_id}
                  onClick={() => setSelectedResult(result)}
                  className={`group relative flex flex-col gap-2 rounded-lg border p-4 cursor-pointer transition-colors shadow-md shadow-black/20 ${
                    isSelected
                      ? "border-primary/50 bg-[#2a2a15]"
                      : "border-border-dark bg-[#232310] hover:bg-[#2a2a15] hover:border-[#686831]"
                  }`}
                >
                  {isSelected && (
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-l-lg"></div>
                  )}

                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className={`flex h-5 items-center rounded px-1.5 text-[10px] font-bold uppercase ${getSimilarityColor(
                          result.similarity_score
                        )}`}
                      >
                        {similarityPercent}% Match
                      </span>
                      <span className="text-xs text-text-muted font-mono">
                        {format(new Date(result.timestamp), "HH:mm:ss.SSS")}
                      </span>
                    </div>
                    <span
                      className={`text-[10px] font-bold border px-1.5 rounded ${getLevelBadgeColor(
                        result.level
                      )}`}
                    >
                      {result.level}
                    </span>
                  </div>

                  <p className="text-sm font-mono text-gray-200 line-clamp-2 leading-relaxed">
                    {result.message}
                  </p>

                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] text-text-muted bg-[#232310] px-1.5 py-0.5 rounded border border-border-dark">
                      srv: {result.service}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* RIGHT PANEL: Analysis & Details */}
        <div className="hidden lg:flex flex-1 flex-col bg-[#1a1a0c] overflow-y-auto">
          {!selectedResult && (
            <div className="flex items-center justify-center h-full text-text-muted">
              <div className="text-center">
                <span className="material-symbols-outlined text-[64px] mb-4">
                  psychology_alt
                </span>
                <p>Select a log to view AI analysis</p>
              </div>
            </div>
          )}

          {selectedResult && (
            <>
              {/* AI Insight Header */}
              <div className="sticky top-0 z-10 bg-[#1a1a0c]/95 backdrop-blur-sm border-b border-border-dark px-8 py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="size-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                    <span className="material-symbols-outlined">
                      psychology_alt
                    </span>
                  </div>
                  <div>
                    <h3 className="text-white font-bold text-lg">
                      AI Analysis
                    </h3>
                    <p className="text-text-muted text-xs">
                      Based on {results.length} semantically similar logs
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button className="flex items-center gap-2 rounded-md bg-[#2a2a15] border border-border-dark hover:border-text-muted px-3 py-1.5 transition-colors">
                    <span className="material-symbols-outlined text-text-muted text-sm">
                      share
                    </span>
                    <span className="text-xs font-medium text-white">
                      Share
                    </span>
                  </button>
                </div>
              </div>

              <div className="p-8 max-w-4xl mx-auto w-full space-y-8">
                {/* Summary Card */}
                <div className="rounded-xl bg-gradient-to-br from-[#2a2a15] to-[#232310] border border-border-dark p-6 relative overflow-hidden group">
                  <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                    <span className="material-symbols-outlined text-8xl text-primary">
                      auto_awesome
                    </span>
                  </div>
                  <div className="relative z-10">
                    <h4 className="text-primary font-bold text-sm mb-3 uppercase tracking-wider flex items-center gap-2">
                      <span className="material-symbols-outlined text-lg">
                        summarize
                      </span>
                      Pattern Summary
                    </h4>
                    <p className="text-gray-200 text-base leading-relaxed">
                      The log shows a{" "}
                      <span className="text-white font-bold">
                        {selectedResult.level.toLowerCase()}
                      </span>{" "}
                      from the{" "}
                      <span className="font-mono text-sm bg-black/30 px-1 rounded text-primary">
                        {selectedResult.service}
                      </span>{" "}
                      service. This appears to be related to{" "}
                      <span className="text-white font-bold">
                        {selectedResult.message.includes("timeout")
                          ? "timeout issues"
                          : selectedResult.message.includes("connection")
                          ? "connection problems"
                          : selectedResult.message.includes("error")
                          ? "error conditions"
                          : "system behavior"}
                      </span>
                      .
                    </p>
                  </div>
                </div>

                {/* Similarity Score */}
                <div className="space-y-2">
                  <h4 className="text-white font-bold text-base">
                    Similarity Score
                  </h4>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 h-2 bg-border-dark rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-primary-alt to-primary transition-all duration-500"
                        style={{
                          width: `${selectedResult.similarity_score * 100}%`,
                        }}
                      ></div>
                    </div>
                    <span className="text-primary font-bold font-mono">
                      {Math.round(selectedResult.similarity_score * 100)}%
                    </span>
                  </div>
                </div>

                {/* Raw Log Viewer */}
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-white font-bold text-base flex items-center gap-2">
                      <span className="material-symbols-outlined text-text-muted">
                        data_object
                      </span>
                      Selected Log Data
                    </h4>
                    <div className="flex gap-2">
                      <button className="text-xs text-text-muted hover:text-white flex items-center gap-1">
                        <span className="material-symbols-outlined text-sm">
                          content_copy
                        </span>{" "}
                        Copy
                      </button>
                    </div>
                  </div>
                  <div className="bg-[#0f0f08] rounded-lg border border-border-dark p-4 overflow-x-auto">
                    <pre className="font-mono text-xs leading-5">
                      <span className="text-gray-500">
                        // Log ID: {selectedResult.log_id}
                      </span>
                      {"\n"}
                      <span className="text-yellow-500">{"{"}</span>
                      {"\n  "}
                      <span className="text-blue-300">"timestamp"</span>:{" "}
                      <span className="text-green-300">
                        "{selectedResult.timestamp}"
                      </span>
                      ,{"\n  "}
                      <span className="text-blue-300">"level"</span>:{" "}
                      <span className="text-red-400">
                        "{selectedResult.level}"
                      </span>
                      ,{"\n  "}
                      <span className="text-blue-300">"service"</span>:{" "}
                      <span className="text-green-300">
                        "{selectedResult.service}"
                      </span>
                      ,
                      {selectedResult.trace_id && (
                        <>
                          {"\n  "}
                          <span className="text-blue-300">
                            "trace_id"
                          </span>:{" "}
                          <span className="text-green-300">
                            "{selectedResult.trace_id}"
                          </span>
                          ,
                        </>
                      )}
                      {"\n  "}
                      <span className="text-blue-300">"message"</span>:{" "}
                      <span className="text-green-300">
                        "{selectedResult.message}"
                      </span>
                      ,{"\n  "}
                      <span className="text-blue-300">
                        "similarity_score"
                      </span>:{" "}
                      <span className="text-orange-300">
                        {selectedResult.similarity_score}
                      </span>
                      {"\n"}
                      <span className="text-yellow-500">{"}"}</span>
                    </pre>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
