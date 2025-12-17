import React, { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { type MetricPoint } from "../../api/types";
import { format, subHours } from "date-fns";

interface MainChartProps {
  data: MetricPoint[];
  loading?: boolean;
}

export const MainChart = ({ data, loading }: MainChartProps) => {
  // Calculate date range for display (12-hour format)
  const dateRange = useMemo(() => {
    const now = new Date();
    const hoursBack = data.length || 24;
    const startDate = subHours(now, hoursBack);
    return {
      start: format(startDate, 'MMM d, HH:mm').toLowerCase(), // e.g., "3am" ha
      end: format(now, 'MMM d, HH:mm').toLowerCase(), // e.g., "4pm"
    };
  }, [data.length]);

  // Format time data to show only military time (HH:mm)
  const formattedData = useMemo(() => {
    return data.map((point) => ({
      ...point,
      displayTime: point.time.includes(':') ? point.time : `${point.time}:00`,
    }));
  }, [data]);

  if (loading) {
    return (
      <div className="relative h-full w-full flex items-center justify-center rounded-xl border border-gray-800/30 bg-gradient-to-br from-primary-alt/5 to-transparent bg-panel-light">
        <div className="flex flex-col items-center gap-3">
          <div className="relative">
            <span className="material-symbols-outlined animate-spin text-primary-alt text-[40px]">
              refresh
            </span>
            <div className="absolute inset-0 rounded-full bg-primary-alt/20 blur-xl animate-pulse"></div>
          </div>
          <span className="text-sm font-medium text-text-muted">Loading Chart Data...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-800/30 bg-gradient-to-br from-primary-alt/5 to-transparent bg-panel-light p-4 relative overflow-hidden group hover:border-gray-700/40 transition-all duration-300 h-full flex flex-col">
      {/* Decorative background elements */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-primary-alt/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none"></div>
      <div className="absolute bottom-0 left-0 w-48 h-48 bg-primary/5 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2 pointer-events-none"></div>
      
      <div className="mb-4 relative z-10 flex-shrink-0">
        {/* Single Header Row with Date Range */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-primary-alt/10 text-primary-alt">
              <span className="material-symbols-outlined text-[20px]">
                monitoring
              </span>
            </div>
            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                Ingestion Throughput
              </h3>
              <p className="text-xs text-text-muted font-medium">
                Logs per second over last 24h
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Date Range Display - Smaller and to the right */}
            <div className="flex items-center gap-1.5 px-2 py-1 bg-gray-800/30 rounded border border-gray-700/40">
              <span className="material-symbols-outlined text-[10px] text-gray-400">schedule</span>
              <span className="text-[10px] font-medium text-gray-400">
                {dateRange.start} — {dateRange.end}
              </span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary-alt/10 border border-gray-800/40">
              <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_8px_rgba(34,211,238,1),0_0_16px_rgba(34,211,238,0.8),0_0_24px_rgba(34,211,238,0.4)]"></span>
              <span className="text-xs font-bold text-primary-alt uppercase tracking-wide">Live</span>
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 w-full relative z-10 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={formattedData}>
            <defs>
              <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorErrors" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorWarns" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#fde047" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#fde047" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#233c48"
              vertical={false}
              opacity={0.5}
            />
            <XAxis
              dataKey="displayTime"
              stroke="#92b7c9"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              minTickGap={30}
              fontWeight={500}
              tickFormatter={(value) => {
                // Convert to 12-hour format (e.g., "3am", "4pm")
                if (typeof value === 'string' && value.includes(':')) {
                  const [hourStr] = value.split(':');
                  const hour = parseInt(hourStr, 10);
                  
                  if (hour === 0) return '12am';
                  if (hour === 12) return '12pm';
                  if (hour < 12) return `${hour}am`;
                  return `${hour - 12}pm`;
                }
                return value;
              }}
            />
            <YAxis
              stroke="#92b7c9"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `${value > 1000 ? (value / 1000).toFixed(1) + 'k' : value}`}
              fontWeight={500}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#0f1419",
                borderColor: "#0ea5e9",
                borderWidth: 1,
                color: "#fff",
                borderRadius: "0.75rem",
                padding: "0.75rem",
                boxShadow: "0 10px 40px rgba(0,0,0,0.5)",
              }}
              itemStyle={{ 
                fontWeight: 600,
                fontSize: "0.875rem",
              }}
              labelStyle={{ 
                color: "#92b7c9", 
                marginBottom: "0.5rem",
                fontWeight: 600,
                fontSize: "0.75rem",
              }}
              cursor={{
                stroke: "#0ea5e9",
                strokeWidth: 2,
                strokeDasharray: "5 5",
              }}
            />
            <Area
              type="monotone"
              dataKey="value"
              name="Total Logs"
              stroke="#0ea5e9"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorValue)"
            />
            <Area
              type="monotone"
              dataKey="errors"
              name="Errors"
              stroke="#ef4444"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorErrors)"
            />
            <Area
              type="monotone"
              dataKey="warns"
              name="Warnings"
              stroke="#fde047"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorWarns)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
