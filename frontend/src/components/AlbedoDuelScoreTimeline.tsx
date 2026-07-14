"use client";

import { useEffect, useMemo, useState } from "react";
import type { AlbedoScoreTimelinePoint } from "@/lib/api";

const HOURS = 24;
const PAD = { top: 20, right: 12, bottom: 40, left: 44 };
const MARKER_R = { normal: 2, active: 2.75, crown: 1.5 };

function fmtScore(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function fmtMargin(n: number): string {
  const pct = n * 100;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function fmtAxisTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function fmtTooltipTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDayLabel(dateKey: string): string {
  const [y, m, d] = dateKey.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function localDateKey(iso: string): string {
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function dayBounds(dateKey: string): { startMs: number; endMs: number } {
  const [y, m, d] = dateKey.split("-").map(Number);
  const start = new Date(y, m - 1, d, 0, 0, 0, 0);
  const end = new Date(y, m - 1, d + 1, 0, 0, 0, 0);
  return { startMs: start.getTime(), endMs: end.getTime() };
}

type ChartPoint = AlbedoScoreTimelinePoint & {
  t: number;
  x: number;
  yCh: number;
  yK: number;
};

type HourTick = { t: number; x: number; label: string; isMidnight: boolean };

function buildChart(
  points: AlbedoScoreTimelinePoint[],
  dateKey: string,
  width: number,
  height: number,
) {
  const { startMs, endMs } = dayBounds(dateKey);
  const windowMs = endMs - startMs;
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  const toX = (ms: number) => PAD.left + ((ms - startMs) / windowMs) * plotW;
  const toY = (score: number) => PAD.top + plotH * (1 - Math.min(1, Math.max(0, score)));

  const chartPoints: ChartPoint[] = points
    .map((p) => {
      const t = new Date(p.finished_at).getTime();
      return {
        ...p,
        t,
        x: toX(t),
        yCh: toY(p.score_challenger),
        yK: toY(p.score_king),
      };
    })
    .filter((p) => p.t >= startMs && p.t < endMs)
    .sort((a, b) => a.t - b.t);

  const hourTicks: HourTick[] = [];
  let cursor = startMs;
  while (cursor < endMs) {
    const d = new Date(cursor);
    hourTicks.push({
      t: cursor,
      x: toX(cursor),
      label: d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false }),
      isMidnight: d.getHours() === 0,
    });
    cursor += 60 * 60 * 1000;
  }

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((v) => ({
    value: v,
    y: toY(v),
    label: `${Math.round(v * 100)}%`,
  }));

  return { chartPoints, hourTicks, yTicks, startMs, endMs, plotW, plotH, toX, toY };
}

function polyline(points: ChartPoint[], key: "yCh" | "yK"): string {
  if (points.length === 0) return "";
  return points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p[key].toFixed(1)}`).join(" ");
}

export default function AlbedoDuelScoreTimeline({
  points,
  requiredWinMargin,
}: {
  points: AlbedoScoreTimelinePoint[];
  referenceAt?: string | null;
  requiredWinMargin?: number | null;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const width = 720;
  const height = 220;

  const availableDates = useMemo(() => {
    const dates = new Set<string>();
    for (const p of points) {
      if (p.finished_at) dates.add(localDateKey(p.finished_at));
    }
    return Array.from(dates).sort();
  }, [points]);

  const defaultDate = availableDates[availableDates.length - 1] ?? localDateKey(new Date().toISOString());
  const [selectedDate, setSelectedDate] = useState(defaultDate);

  useEffect(() => {
    if (availableDates.length === 0) return;
    if (!availableDates.includes(selectedDate)) {
      setSelectedDate(availableDates[availableDates.length - 1]);
    }
  }, [availableDates, selectedDate]);

  const dayPoints = useMemo(
    () => points.filter((p) => localDateKey(p.finished_at) === selectedDate),
    [points, selectedDate],
  );

  const chart = useMemo(
    () => buildChart(dayPoints, selectedDate, width, height),
    [dayPoints, selectedDate],
  );

  const stats = useMemo(() => {
    const { chartPoints } = chart;
    if (chartPoints.length === 0) return null;
    const chAvg = chartPoints.reduce((s, p) => s + p.score_challenger, 0) / chartPoints.length;
    const kAvg = chartPoints.reduce((s, p) => s + p.score_king, 0) / chartPoints.length;
    const chWins = chartPoints.filter((p) => p.challenger_won).length;
    return {
      count: chartPoints.length,
      chAvg,
      kAvg,
      chWinPct: (chWins / chartPoints.length) * 100,
      coronations: chartPoints.filter((p) => p.coronated).length,
    };
  }, [chart]);

  const active = chart.chartPoints.find((p) => p.eval_run_id === hovered) ?? null;
  const winBarY =
    requiredWinMargin != null && Number.isFinite(requiredWinMargin)
      ? chart.toY(requiredWinMargin)
      : null;

  const dateIdx = availableDates.indexOf(selectedDate);
  const canPrev = dateIdx > 0;
  const canNext = dateIdx >= 0 && dateIdx < availableDates.length - 1;

  return (
    <section className="panel px-3 py-2.5">
      <div className="flex flex-wrap items-end justify-between gap-2 mb-2">
        <div>
          <h3 className="text-[11px] font-semibold text-zinc-200">Daily score timeline</h3>
          <p className="text-[9px] text-zinc-600 mt-0.5">
            Challenger vs king scores by duel finish time · {HOURS}h day view
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            disabled={!canPrev}
            onClick={() => canPrev && setSelectedDate(availableDates[dateIdx - 1])}
            className="px-1.5 py-0.5 rounded border border-zinc-700 text-[10px] text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 disabled:opacity-30 disabled:cursor-not-allowed"
            aria-label="Previous day with duels"
          >
            ‹
          </button>
          <input
            type="date"
            value={selectedDate}
            min={availableDates[0]}
            max={availableDates[availableDates.length - 1]}
            onChange={(e) => e.target.value && setSelectedDate(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-900/80 px-2 py-0.5 text-[10px] text-zinc-200 mono focus:outline-none focus:border-emerald-500/40"
          />
          <button
            type="button"
            disabled={!canNext}
            onClick={() => canNext && setSelectedDate(availableDates[dateIdx + 1])}
            className="px-1.5 py-0.5 rounded border border-zinc-700 text-[10px] text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 disabled:opacity-30 disabled:cursor-not-allowed"
            aria-label="Next day with duels"
          >
            ›
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <p className="text-[9px] text-zinc-500">{fmtDayLabel(selectedDate)}</p>
        {stats ? (
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[9px] mono">
            <span className="text-zinc-500">
              <span className="text-zinc-300">{stats.count}</span> duels
            </span>
            <span className="text-rose-300/90">ch {fmtScore(stats.chAvg)}</span>
            <span className="text-emerald-300/90">k {fmtScore(stats.kAvg)}</span>
            <span className="text-zinc-500">ch win {stats.chWinPct.toFixed(0)}%</span>
            {stats.coronations > 0 && (
              <span className="text-amber-400/90">{stats.coronations} crown</span>
            )}
          </div>
        ) : (
          <span className="text-[9px] text-zinc-600">No duels this day</span>
        )}
      </div>

      <div className="flex flex-wrap gap-3 text-[9px] mb-2">
        <span className="flex items-center gap-1.5 text-zinc-500">
          <span className="w-4 h-0.5 bg-rose-400 rounded" />
          <span className="text-rose-300/90">Challenger</span>
        </span>
        <span className="flex items-center gap-1.5 text-zinc-500">
          <span className="w-4 h-0.5 bg-emerald-400 rounded" />
          <span className="text-emerald-300/90">King</span>
        </span>
        {winBarY != null && (
          <span className="flex items-center gap-1.5 text-zinc-500">
            <span className="w-4 h-px border-t border-dashed border-amber-400/70" />
            <span className="text-amber-300/80">Win bar {fmtScore(requiredWinMargin!)}</span>
          </span>
        )}
        <span className="flex items-center gap-1.5 text-zinc-600">
          <span className="w-1.5 h-1.5 rounded-full border border-amber-400/60 bg-amber-500/20" />
          coronation
        </span>
      </div>

      {availableDates.length === 0 ? (
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 px-4 py-8 text-center text-[10px] text-zinc-600">
          No finished duels available
        </div>
      ) : chart.chartPoints.length === 0 ? (
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 px-4 py-8 text-center text-[10px] text-zinc-600">
          No duels on {fmtDayLabel(selectedDate)}
        </div>
      ) : (
        <div className="relative w-full overflow-x-auto">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full min-w-[320px] h-auto select-none"
            role="img"
            aria-label={`Duel score timeline for ${selectedDate}`}
          >
            <defs>
              <linearGradient id="timeline-night" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="rgb(24 24 27 / 0.15)" />
                <stop offset="100%" stopColor="rgb(24 24 27 / 0)" />
              </linearGradient>
            </defs>

            {chart.hourTicks.map((tick) => {
              const hour = new Date(tick.t).getHours();
              const isDay = hour >= 6 && hour < 18;
              const nextX =
                chart.hourTicks.find((h) => h.t > tick.t)?.x ?? PAD.left + chart.plotW;
              const bandW = Math.max(0, nextX - tick.x);
              if (bandW < 2) return null;
              return (
                <rect
                  key={`band-${tick.t}`}
                  x={tick.x}
                  y={PAD.top}
                  width={bandW}
                  height={chart.plotH}
                  fill={isDay ? "rgb(250 204 21 / 0.03)" : "url(#timeline-night)"}
                />
              );
            })}

            {chart.yTicks.map((tick) => (
              <g key={tick.value}>
                <line
                  x1={PAD.left}
                  y1={tick.y}
                  x2={PAD.left + chart.plotW}
                  y2={tick.y}
                  stroke="rgb(63 63 70 / 0.45)"
                  strokeDasharray={tick.value === 0.5 ? "4 3" : "2 4"}
                />
                <text
                  x={PAD.left - 6}
                  y={tick.y + 3}
                  textAnchor="end"
                  className="fill-zinc-600"
                  fontSize="9"
                  fontFamily="ui-monospace, monospace"
                >
                  {tick.label}
                </text>
              </g>
            ))}

            {winBarY != null && (
              <line
                x1={PAD.left}
                y1={winBarY}
                x2={PAD.left + chart.plotW}
                y2={winBarY}
                stroke="rgb(251 191 36 / 0.45)"
                strokeWidth="1"
                strokeDasharray="5 4"
              />
            )}

            {chart.hourTicks.map((tick) => (
              <g key={tick.t}>
                <line
                  x1={tick.x}
                  y1={PAD.top}
                  x2={tick.x}
                  y2={PAD.top + chart.plotH}
                  stroke={tick.isMidnight ? "rgb(113 113 122 / 0.5)" : "rgb(63 63 70 / 0.35)"}
                  strokeWidth={tick.isMidnight ? 1 : 0.5}
                />
                <text
                  x={tick.x}
                  y={height - 8}
                  textAnchor="middle"
                  className={tick.isMidnight ? "fill-zinc-400" : "fill-zinc-600"}
                  fontSize="8"
                  fontFamily="ui-monospace, monospace"
                >
                  {tick.label}
                </text>
              </g>
            ))}

            <path
              d={polyline(chart.chartPoints, "yCh")}
              fill="none"
              stroke="rgb(251 113 133 / 0.85)"
              strokeWidth="1.5"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <path
              d={polyline(chart.chartPoints, "yK")}
              fill="none"
              stroke="rgb(52 211 153 / 0.85)"
              strokeWidth="1.5"
              strokeLinejoin="round"
              strokeLinecap="round"
            />

            {chart.chartPoints.map((p) => {
              const isActive = hovered === p.eval_run_id;
              const r = isActive ? MARKER_R.active : MARKER_R.normal;
              return (
                <g
                  key={p.eval_run_id}
                  onMouseEnter={() => setHovered(p.eval_run_id)}
                  onMouseLeave={() => setHovered(null)}
                  className="cursor-pointer"
                >
                  <line
                    x1={p.x}
                    y1={p.yCh}
                    x2={p.x}
                    y2={p.yK}
                    stroke="rgb(113 113 122 / 0.3)"
                    strokeWidth="0.75"
                  />
                  <circle
                    cx={p.x}
                    cy={p.yCh}
                    r={r}
                    fill={p.challenger_won ? "rgb(251 113 133)" : "rgb(39 39 42)"}
                    stroke="rgb(251 113 133)"
                    strokeWidth={isActive ? 1.25 : 0.75}
                  />
                  <circle
                    cx={p.x}
                    cy={p.yK}
                    r={r}
                    fill={p.challenger_won ? "rgb(39 39 42)" : "rgb(52 211 153)"}
                    stroke="rgb(52 211 153)"
                    strokeWidth={isActive ? 1.25 : 0.75}
                  />
                  {p.coronated && (
                    <circle
                      cx={p.x}
                      cy={Math.min(p.yCh, p.yK) - 5}
                      r={MARKER_R.crown}
                      fill="rgb(251 191 36 / 0.9)"
                      stroke="rgb(251 191 36)"
                      strokeWidth="0.5"
                    />
                  )}
                  <rect
                    x={p.x - 6}
                    y={PAD.top}
                    width={12}
                    height={chart.plotH}
                    fill="transparent"
                  />
                </g>
              );
            })}

            <rect
              x={PAD.left}
              y={PAD.top}
              width={chart.plotW}
              height={chart.plotH}
              fill="none"
              stroke="rgb(63 63 70 / 0.5)"
              rx="2"
            />
          </svg>

          {active && (
            <div className="absolute top-2 right-2 max-w-[240px] rounded-md border border-zinc-700/80 bg-zinc-950/95 px-2.5 py-2 text-[9px] shadow-lg backdrop-blur-sm pointer-events-none">
              <p className="text-zinc-400 mono">{fmtTooltipTime(active.finished_at)}</p>
              <div className="mt-1.5 space-y-1">
                <p className="text-rose-300">
                  ch uid {active.challenger_uid}{" "}
                  <span className="mono font-medium">{fmtScore(active.score_challenger)}</span>
                  <span className="block text-zinc-600 truncate" title={active.challenger_label}>
                    {active.challenger_label}
                  </span>
                </p>
                <p className="text-emerald-300">
                  k uid {active.king_uid ?? "—"}{" "}
                  <span className="mono font-medium">{fmtScore(active.score_king)}</span>
                  <span className="block text-zinc-600 truncate" title={active.king_label}>
                    {active.king_label}
                  </span>
                </p>
              </div>
              <p className="mt-1.5 text-zinc-500">
                margin{" "}
                <span className={`mono ${active.challenger_won ? "text-rose-300" : "text-emerald-300"}`}>
                  {fmtMargin(active.win_margin)}
                </span>
                {active.coronated && <span className="ml-1 text-amber-400">crowned</span>}
              </p>
            </div>
          )}
        </div>
      )}

      {chart.chartPoints.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-0.5">
          {chart.chartPoints.map((p) => (
            <button
              key={p.eval_run_id}
              type="button"
              title={`${fmtAxisTime(p.finished_at)} · ch ${fmtScore(p.score_challenger)} · k ${fmtScore(p.score_king)}`}
              onMouseEnter={() => setHovered(p.eval_run_id)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(p.eval_run_id)}
              onBlur={() => setHovered(null)}
              className={`h-1 rounded-sm transition-all ${
                hovered === p.eval_run_id
                  ? "w-3 bg-zinc-400"
                  : p.challenger_won
                    ? "w-1.5 bg-rose-500/70"
                    : "w-1.5 bg-emerald-500/70"
              } ${p.coronated ? "ring-1 ring-amber-400/50" : ""}`}
            />
          ))}
        </div>
      )}

      {availableDates.length > 1 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {availableDates.map((d) => {
            const count = points.filter((p) => localDateKey(p.finished_at) === d).length;
            const active = d === selectedDate;
            return (
              <button
                key={d}
                type="button"
                onClick={() => setSelectedDate(d)}
                className={`rounded px-1.5 py-0.5 text-[9px] mono border transition-colors ${
                  active
                    ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-200"
                    : "border-zinc-800 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300"
                }`}
                title={`${fmtDayLabel(d)} · ${count} duels`}
              >
                {d.slice(5)} <span className="text-zinc-600">({count})</span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
