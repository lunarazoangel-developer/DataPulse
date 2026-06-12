'use client'

import { CSSProperties } from 'react'

export type PulseColor = 'blue' | 'red' | 'yellow' | 'green'

const COLOR_MAP: Record<PulseColor, { stroke: string; glow: string; track: string }> = {
  blue: {
    stroke: '#3b82f6',
    glow: 'rgba(59, 130, 246, 0.55)',
    track: 'rgba(59, 130, 246, 0.22)',
  },
  red: {
    stroke: '#ef4444',
    glow: 'rgba(239, 68, 68, 0.55)',
    track: 'rgba(239, 68, 68, 0.22)',
  },
  yellow: {
    stroke: '#eab308',
    glow: 'rgba(234, 179, 8, 0.55)',
    track: 'rgba(234, 179, 8, 0.22)',
  },
  green: {
    stroke: '#22c55e',
    glow: 'rgba(34, 197, 94, 0.55)',
    track: 'rgba(34, 197, 94, 0.22)',
  },
}

const ECG_PATH =
  'M 0 50 L 80 50 L 95 50 L 105 62 L 115 50 L 135 50 L 145 10 L 155 90 L 165 50 L 220 50 L 320 50'

const ECG_PATH_COMPACT =
  'M 0 50 L 30 50 L 38 60 L 46 50 L 60 50 L 68 12 L 76 88 L 84 50 L 100 50'

interface PulseBarProps {
  color?: PulseColor
  width?: number | string
  height?: number | string
  animate?: boolean
  showTrack?: boolean
  compact?: boolean
  className?: string
  ariaLabel?: string
}

export default function PulseBar({
  color = 'blue',
  width = '100%',
  height = 28,
  animate = true,
  showTrack = true,
  compact = false,
  className,
  ariaLabel,
}: PulseBarProps) {
  const palette = COLOR_MAP[color]
  const path = compact ? ECG_PATH_COMPACT : ECG_PATH
  const viewBox = compact ? '0 0 100 100' : '0 0 320 100'
  const dashLen = compact ? 120 : 240
  const strokeW = compact ? 2.5 : 3
  const sparkR = compact ? 2.5 : 5
  const sparkCx = compact ? 0 : 0
  const sparkCy = compact ? 50 : 50
  const resolvedWidth = compact ? 36 : width
  const resolvedHeight = compact ? 20 : height

  const containerStyle: CSSProperties = {
    width: resolvedWidth,
    height: resolvedHeight,
    display: 'inline-flex',
    alignItems: 'center',
    flexShrink: 0,
  }

  return (
    <div
      className={className}
      style={containerStyle}
      role={ariaLabel ? 'img' : undefined}
      aria-label={ariaLabel}
      aria-hidden={ariaLabel ? undefined : true}
    >
      <svg
        viewBox={viewBox}
        preserveAspectRatio="none"
        width="100%"
        height="100%"
        style={{ overflow: 'visible', display: 'block' }}
      >
        {showTrack && !compact && (
          <path
            d={path}
            fill="none"
            stroke={palette.track}
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        <path
          d={path}
          fill="none"
          stroke={palette.stroke}
          strokeWidth={strokeW}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            filter: `drop-shadow(0 0 4px ${palette.stroke}) drop-shadow(0 0 12px ${palette.glow})`,
            strokeDasharray: `${dashLen} ${dashLen}`,
            strokeDashoffset: animate ? undefined : 0,
            animation: animate ? 'pulse-dash 1.6s linear infinite' : 'none',
          }}
        />
        <circle
          cx={sparkCx}
          cy={sparkCy}
          r={sparkR}
          fill={palette.stroke}
          style={{
            filter: `drop-shadow(0 0 6px ${palette.stroke}) drop-shadow(0 0 16px ${palette.stroke})`,
            opacity: animate ? undefined : 1,
            animation: animate ? 'spark 1.6s linear infinite' : 'none',
          }}
        />
      </svg>
    </div>
  )
}
