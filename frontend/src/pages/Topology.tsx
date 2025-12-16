import React, { useState } from 'react';

export const Topology = () => {
  const [zoom, setZoom] = useState(1);

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.2, 2));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.2, 0.5));
  const handleFitToScreen = () => setZoom(1);

  return (
    <div className="h-full -m-6 flex flex-col">
      {/* Page Title Bar */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-border-dark bg-white dark:bg-surface-dark">
        <h1 className="text-xl font-semibold tracking-tight flex items-center gap-2 text-gray-900 dark:text-white">
          <span className="material-symbols-outlined text-primary">hub</span>
          System Architecture - Data Flow
        </h1>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-text-muted bg-gray-100 dark:bg-background-dark px-3 py-1.5 rounded border border-gray-300 dark:border-border-dark">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
            12.4k logs/sec
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">
            {(zoom * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      {/* Topology Canvas */}
      <div className="flex-1 relative bg-[#0a0c10] overflow-hidden">
        {/* Grid background */}
        <div
          className="absolute inset-0 z-0 opacity-20 pointer-events-none"
          style={{
            backgroundImage: 'radial-gradient(#333 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        ></div>

        {/* Main content area */}
        <div 
          className="relative z-10 w-full h-full flex items-center justify-center transition-transform duration-300"
          style={{ transform: `scale(${zoom})` }}
        >
          <div className="relative w-[1200px] h-[400px]">
            {/* SVG Layer for Arrows - ABOVE the cards */}
            <svg className="absolute inset-0 w-full h-full z-30 pointer-events-none" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <polygon points="0 0, 8 4, 0 8" fill="#FACC15" />
                </marker>
                <marker id="arrow-gray" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <polygon points="0 0, 8 4, 0 8" fill="#6B7280" />
                </marker>
              </defs>

              {/* Generator → Kafka */}
              <path 
                d="M 150 200 L 230 200" 
                stroke="#FACC15" 
                strokeWidth="2" 
                fill="none" 
                markerEnd="url(#arrow)"
                strokeDasharray="8 4"
                className="flow-line"
              />

              {/* Kafka → Consumer */}
              <path 
                d="M 350 200 L 430 200" 
                stroke="#FACC15" 
                strokeWidth="2" 
                fill="none" 
                markerEnd="url(#arrow)"
                strokeDasharray="8 4"
                className="flow-line"
                style={{ animationDelay: '0.3s' }}
              />

              {/* Consumer → ClickHouse (top path) */}
              <path 
                d="M 530 180 L 630 140" 
                stroke="#FACC15" 
                strokeWidth="2" 
                fill="none" 
                markerEnd="url(#arrow)"
                strokeDasharray="8 4"
                className="flow-line"
                style={{ animationDelay: '0.6s' }}
              />

              {/* Consumer → Vector Queue (bottom path) */}
              <path 
                d="M 530 220 L 630 260" 
                stroke="#6B7280" 
                strokeWidth="2" 
                fill="none" 
                markerEnd="url(#arrow-gray)"
                strokeDasharray="5 3"
              />

              {/* Vector Queue → Vector Worker */}
              <path 
                d="M 750 260 L 830 260" 
                stroke="#8B5CF6" 
                strokeWidth="2" 
                fill="none" 
                markerEnd="url(#arrow)"
                strokeDasharray="8 4"
                className="flow-line"
                style={{ animationDelay: '0.9s' }}
              />

              {/* Vector Worker → Jina (top) */}
              <path 
                d="M 930 240 L 1010 190" 
                stroke="#8B5CF6" 
                strokeWidth="2" 
                fill="none" 
                markerEnd="url(#arrow)"
                strokeDasharray="5 3"
              />

              {/* Jina ↔ Redis */}
              <path 
                d="M 1070 160 L 1070 90" 
                stroke="#EF4444" 
                strokeWidth="2" 
                fill="none" 
                markerEnd="url(#arrow)"
                strokeDasharray="3 2"
              />

              {/* Vector Worker → Qdrant (bottom) */}
              <path 
                d="M 930 280 L 1010 310" 
                stroke="#FACC15" 
                strokeWidth="2" 
                fill="none" 
                markerEnd="url(#arrow)"
                strokeDasharray="8 4"
                className="flow-line"
                style={{ animationDelay: '1.2s' }}
              />
            </svg>

            {/* Node Cards Layer - positioned precisely */}
            
            {/* 1. Log Generator */}
            <div className="absolute left-[30px] top-[170px] bg-[#1a1d24] border-2 border-green-500/60 rounded-lg p-3 w-[110px] shadow-xl z-20 cursor-pointer group hover:border-green-500 hover:shadow-green-500/30 transition-all">
              <div className="text-[9px] text-green-400 uppercase font-bold mb-1 tracking-wide">SOURCE</div>
              <div className="text-xs font-bold text-white leading-tight">Log</div>
              <div className="text-xs font-bold text-white leading-tight mb-1">Generator</div>
              <div className="text-[8px] text-gray-400 font-mono">50 logs/s</div>
            </div>

            {/* 2. Kafka */}
            <div className="absolute left-[240px] top-[170px] bg-[#1a1d24] border-2 border-blue-500/60 rounded-lg p-3 w-[100px] shadow-xl z-20 cursor-pointer group hover:border-blue-500 hover:shadow-blue-500/30 transition-all">
              <div className="text-[9px] text-blue-400 uppercase font-bold mb-1 tracking-wide">QUEUE</div>
              <div className="text-xs font-bold text-white leading-tight mb-1">Kafka</div>
              <div className="text-[8px] text-gray-400">raw-logs</div>
              <div className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-[9px] text-white font-bold">
                1
              </div>
            </div>

            {/* 3. Consumer */}
            <div className="absolute left-[440px] top-[170px] bg-[#1a1d24] border-2 border-cyan-500/60 rounded-lg p-3 w-[90px] shadow-xl z-20 cursor-pointer group hover:border-cyan-500 hover:shadow-cyan-500/30 transition-all">
              <div className="text-[9px] text-cyan-400 uppercase font-bold mb-1 tracking-wide">CONSUMER</div>
              <div className="text-xs font-bold text-white leading-tight mb-1">Batch</div>
              <div className="text-[8px] text-gray-400 font-mono">1K/batch</div>
            </div>

            {/* 4. ClickHouse (top branch) */}
            <div className="absolute left-[640px] top-[110px] bg-[#1a1d24] border-2 border-orange-500/60 rounded-lg p-3 w-[110px] shadow-xl z-20 cursor-pointer group hover:border-orange-500 hover:shadow-orange-500/30 transition-all">
              <div className="text-[9px] text-orange-400 uppercase font-bold mb-1 tracking-wide">STORAGE</div>
              <div className="text-xs font-bold text-white leading-tight mb-1">ClickHouse</div>
              <div className="text-[8px] text-gray-400">All logs</div>
              <div className="absolute top-1 right-1">
                <span className="flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-orange-500"></span>
                </span>
              </div>
            </div>

            {/* 5. Vectorization Queue (bottom branch) */}
            <div className="absolute left-[640px] top-[230px] bg-[#1a1d24] border-2 border-purple-500/60 rounded-lg p-3 w-[100px] shadow-xl z-20 cursor-pointer group hover:border-purple-500 hover:shadow-purple-500/30 transition-all">
              <div className="text-[9px] text-purple-400 uppercase font-bold mb-1 tracking-wide">QUEUE</div>
              <div className="text-xs font-bold text-white leading-tight mb-1">Vector</div>
              <div className="text-[8px] text-gray-400">ERR/WARN</div>
            </div>

            {/* 6. Vector Worker */}
            <div className="absolute left-[840px] top-[230px] bg-[#1a1d24] border-2 border-purple-500/60 rounded-lg p-3 w-[90px] shadow-xl z-20 cursor-pointer group hover:border-purple-500 hover:shadow-purple-500/30 transition-all">
              <div className="text-[9px] text-purple-400 uppercase font-bold mb-1 tracking-wide">WORKER</div>
              <div className="text-xs font-bold text-white leading-tight mb-1">Vector</div>
              <div className="text-[8px] text-gray-400 font-mono">10/batch</div>
            </div>

            {/* 7. Jina Embeddings */}
            <div className="absolute left-[1020px] top-[160px] bg-[#1a1d24] border-2 border-purple-500/60 rounded-lg p-3 w-[90px] shadow-xl z-20 cursor-pointer group hover:border-purple-500 hover:shadow-purple-500/30 transition-all">
              <div className="text-[9px] text-purple-400 uppercase font-bold mb-1 tracking-wide">AI MODEL</div>
              <div className="text-xs font-bold text-white leading-tight mb-1">Jina v3</div>
              <div className="text-[8px] text-gray-400">768-dim</div>
            </div>

            {/* 8. Redis Cache */}
            <div className="absolute left-[1020px] top-[50px] bg-[#1a1d24] border-2 border-red-500/60 rounded-lg p-2.5 w-[90px] shadow-xl z-20 cursor-pointer group hover:border-red-500 hover:shadow-red-500/30 transition-all">
              <div className="text-[9px] text-red-400 uppercase font-bold mb-1 tracking-wide">CACHE</div>
              <div className="text-xs font-bold text-white leading-tight mb-1">Redis</div>
              <div className="text-[8px] text-gray-400">90% hits</div>
            </div>

            {/* 9. Qdrant */}
            <div className="absolute left-[1020px] top-[280px] bg-[#1a1d24] border-2 border-pink-500/60 rounded-lg p-3 w-[90px] shadow-xl z-20 cursor-pointer group hover:border-pink-500 hover:shadow-pink-500/30 transition-all">
              <div className="text-[9px] text-pink-400 uppercase font-bold mb-1 tracking-wide">VECTOR DB</div>
              <div className="text-xs font-bold text-white leading-tight mb-1">Qdrant</div>
              <div className="text-[8px] text-gray-400">HNSW</div>
            </div>

            {/* Arrow labels - positioned on the lines */}
            <div className="absolute left-[165px] top-[185px] text-[9px] text-primary font-mono font-bold z-40 bg-[#0a0c10] px-1">
              50/s
            </div>
            
            <div className="absolute left-[365px] top-[185px] text-[9px] text-primary font-mono font-bold z-40 bg-[#0a0c10] px-1">
              batch
            </div>
            
            <div className="absolute left-[560px] top-[150px] text-[9px] text-orange-400 font-mono font-bold z-40 bg-[#0a0c10] px-1">
              ALL
            </div>
            
            <div className="absolute left-[560px] top-[235px] text-[9px] text-gray-400 font-mono text-[8px] z-40 bg-[#0a0c10] px-1">
              if ERROR
            </div>
            
            <div className="absolute left-[765px] top-[245px] text-[9px] text-purple-400 font-mono font-bold z-40 bg-[#0a0c10] px-1">
              embed
            </div>
            
            <div className="absolute left-[950px] top-[215px] text-[9px] text-purple-400 font-mono text-[8px] z-40 bg-[#0a0c10] px-1">
              request
            </div>
            
            <div className="absolute left-[1045px] top-[110px] text-[9px] text-red-400 font-mono text-[8px] z-40 bg-[#0a0c10] px-1">
              cache
            </div>
            
            <div className="absolute left-[950px] top-[285px] text-[9px] text-pink-400 font-mono font-bold z-40 bg-[#0a0c10] px-1">
              store
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="absolute bottom-6 right-6 bg-[#1a1d24]/95 backdrop-blur border border-gray-700 p-4 rounded-xl shadow-xl z-40 w-48">
          <h3 className="text-xs font-bold text-gray-400 uppercase mb-3 tracking-wider">Service Types</h3>
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-gray-300">
              <span className="w-2 h-2 rounded-sm bg-green-500"></span>
              <span>Log Source</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-300">
              <span className="w-2 h-2 rounded-sm bg-blue-500"></span>
              <span>Message Queue</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-300">
              <span className="w-2 h-2 rounded-sm bg-cyan-500"></span>
              <span>Processor</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-300">
              <span className="w-2 h-2 rounded-sm bg-orange-500"></span>
              <span>Storage (Logs)</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-300">
              <span className="w-2 h-2 rounded-sm bg-purple-500"></span>
              <span>AI/ML Pipeline</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-300">
              <span className="w-2 h-2 rounded-sm bg-pink-500"></span>
              <span>Vector Storage</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-300">
              <span className="w-2 h-2 rounded-sm bg-red-500"></span>
              <span>Cache Layer</span>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-gray-700">
            <div className="flex items-center gap-2 text-xs text-gray-300 mb-1">
              <div className="w-4 h-[2px] bg-primary"></div>
              <span>Active Flow</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-300">
              <div className="w-4 h-[2px] bg-gray-600" style={{ borderTop: '2px dashed #6B7280', height: 0 }}></div>
              <span>Conditional</span>
            </div>
          </div>
        </div>

        {/* Zoom Controls */}
        <div className="absolute bottom-6 left-6 flex flex-col gap-2 z-40">
          <div className="bg-[#1a1d24]/95 backdrop-blur border border-gray-700 rounded-lg flex flex-col overflow-hidden shadow-lg">
            <button 
              onClick={handleZoomIn}
              className="p-2 hover:bg-gray-700 text-gray-400 hover:text-primary transition-colors border-b border-gray-700 group cursor-pointer"
              title="Zoom In"
            >
              <span className="material-symbols-outlined text-lg group-hover:scale-110 transition-transform inline-block">add</span>
            </button>
            <button 
              onClick={handleZoomOut}
              className="p-2 hover:bg-gray-700 text-gray-400 hover:text-primary transition-colors group cursor-pointer"
              title="Zoom Out"
            >
              <span className="material-symbols-outlined text-lg group-hover:scale-110 transition-transform inline-block">remove</span>
            </button>
          </div>
          <button
            onClick={handleFitToScreen}
            className="bg-[#1a1d24]/95 backdrop-blur border border-gray-700 rounded-lg p-2 hover:bg-gray-700 text-gray-400 hover:text-primary transition-colors shadow-lg group cursor-pointer"
            title="Reset View"
          >
            <span className="material-symbols-outlined text-lg group-hover:scale-110 transition-transform inline-block">center_focus_strong</span>
          </button>
        </div>

        {/* Flow Info */}
        <div className="absolute top-6 right-6 bg-[#1a1d24]/95 backdrop-blur border border-gray-700 p-3 rounded-xl shadow-xl z-40 max-w-[280px]">
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined text-sm text-primary mt-0.5">info</span>
            <div className="text-[10px] text-gray-300 leading-relaxed">
              <span className="text-white font-bold block mb-1">Event-Driven Pipeline</span>
              All logs → ClickHouse. ERROR/WARN logs → AI vectorization → Qdrant for semantic search.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
