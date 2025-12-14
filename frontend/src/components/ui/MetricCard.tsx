import React from 'react';

interface MetricCardProps {
  label: string;
  value: string | number;
  icon: string;
  trend?: string;
  loading?: boolean;
  variant?: 'default' | 'highlight';
}

export const MetricCard = ({ label, value, icon, trend, loading, variant = 'default' }: MetricCardProps) => {
  const isHighlight = variant === 'highlight';
  
  return (
    <div
      className={`relative overflow-hidden rounded-xl p-5 shadow-sm group transition-all duration-300 ${
        isHighlight
          ? 'bg-white dark:bg-surface-dark border border-primary/30 dark:border-primary/30 shadow-[0_0_15px_rgba(253,224,71,0.05)]'
          : 'bg-white dark:bg-surface-dark border border-gray-200 dark:border-gray-800'
      }`}
    >
      {isHighlight && (
        <div className="absolute top-0 right-0 w-16 h-16 bg-primary/10 rounded-bl-full -mr-4 -mt-4"></div>
      )}
      
      <div className="flex justify-between items-start mb-4">
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            {label}
          </p>
          {loading ? (
            <div className="h-9 w-24 rounded bg-gray-200 dark:bg-gray-700 animate-pulse mt-1"></div>
          ) : (
            <h3 className={`text-3xl font-bold mt-1 ${isHighlight ? 'text-primary drop-shadow-sm' : 'text-gray-900 dark:text-white'}`}>
              {value}
            </h3>
          )}
        </div>
        {isHighlight && (
          <span className="material-icons-outlined text-primary text-xl animate-pulse">
            {icon}
          </span>
        )}
        {!isHighlight && !loading && (
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
          </span>
        )}
      </div>

      {trend && !loading && (
        <div className={`text-xs font-medium ${isHighlight ? 'text-primary/80' : 'text-gray-500 dark:text-gray-400'}`}>
          {trend}
        </div>
      )}

      {/* Mini sparkline for default variant */}
      {!isHighlight && !loading && (
        <div className="h-12 w-full flex items-end gap-1 opacity-50 mt-2">
          {[30, 50, 40, 70, 60, 85, 75, 65, 55, 45].map((height, i) => (
            <div
              key={i}
              className={`w-1 rounded-t-sm ${
                i === 5 ? 'bg-primary shadow-[0_0_10px_rgba(253,224,71,0.5)]' : 'bg-gray-300 dark:bg-gray-700'
              }`}
              style={{ height: `${height}%` }}
            ></div>
          ))}
        </div>
      )}

      {isHighlight && (
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mb-2 mt-4">
          <div className="bg-primary h-1.5 rounded-full" style={{ width: '85%' }}></div>
        </div>
      )}
    </div>
  );
};
