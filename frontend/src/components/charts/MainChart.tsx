import React from "react";
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

interface MainChartProps {
  data: MetricPoint[];
  loading?: boolean;
}

export const MainChart = ({ data, loading }: MainChartProps) => {
  if (loading) {
    return (
      <div className="relative h-[300px] w-full flex items-center justify-center rounded-xl border border-border-dark bg-panel-light">
        <div className="flex items-center gap-2 text-sm text-text-muted animate-pulse">
          <span className="material-symbols-outlined animate-spin">
            refresh
          </span>
          Loading Data...
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border-dark bg-panel-light p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-white">Ingestion Throughput</h3>
          <p className="text-xs text-text-muted">
            Logs per second over last 24h
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 text-xs font-bold text-primary">
            <span className="h-2 w-2 rounded-full bg-primary animate-pulse"></span>{" "}
            Live
          </span>
        </div>
      </div>

      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#facc15" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#facc15" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#233c48"
              vertical={false}
            />
            <XAxis
              dataKey="time"
              stroke="#92b7c9"
              fontSize={12}
              tickLine={false}
              axisLine={false}
              minTickGap={30}
            />
            <YAxis
              stroke="#92b7c9"
              fontSize={12}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `${value / 1000}k`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#16232b",
                borderColor: "#233c48",
                color: "#fff",
              }}
              itemStyle={{ color: "#facc15" }}
              labelStyle={{ color: "#92b7c9", marginBottom: "0.5rem" }}
              cursor={{
                stroke: "#facc15",
                strokeWidth: 1,
                strokeDasharray: "3 3",
              }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#facc15"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorValue)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
