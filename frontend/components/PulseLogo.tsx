'use client'

import { CSSProperties } from 'react'
import PulseBar from './PulseBar'

export type PulseLogoSize = 'sm' | 'md' | 'lg'

interface SizeConfig {
  wordmarkFontSize: string
  pulseWidth: string
  pulseHeight: string
  gap: string
}

const SIZES: Record<PulseLogoSize, SizeConfig> = {
  sm: {
    wordmarkFontSize: 'clamp(20px, 2.4vw, 28px)',
    pulseWidth: '90px',
    pulseHeight: '32px',
    gap: '10px',
  },
  md: {
    wordmarkFontSize: 'clamp(40px, 6vw, 72px)',
    pulseWidth: '200px',
    pulseHeight: '60px',
    gap: '20px',
  },
  lg: {
    wordmarkFontSize: 'clamp(56px, 8vw, 96px)',
    pulseWidth: '260px',
    pulseHeight: '76px',
    gap: '24px',
  },
}

interface PulseLogoProps {
  size?: PulseLogoSize
  showWordmark?: boolean
  showPulse?: boolean
  animate?: boolean
  withHalo?: boolean
  className?: string
  ariaLabel?: string
}

export default function PulseLogo({
  size = 'md',
  showWordmark = true,
  showPulse = true,
  animate = true,
  withHalo = false,
  className,
  ariaLabel = 'DataPulse',
}: PulseLogoProps) {
  const cfg = SIZES[size]

  const containerStyle: CSSProperties = {
    position: 'relative',
    display: 'inline-flex',
    alignItems: 'center',
    gap: cfg.gap,
    userSelect: 'none',
    paddingBottom: withHalo ? '20px' : undefined,
  }

  return (
    <div className={className} style={containerStyle} role="img" aria-label={ariaLabel}>
      {withHalo && (
        <div
          aria-hidden
          style={{
            position: 'absolute',
            inset: '-40% -10% -10% -10%',
            background:
              'radial-gradient(55% 40% at 50% 55%, rgba(59, 130, 246, 0.18), transparent 70%)',
            zIndex: -1,
            pointerEvents: 'none',
          }}
        />
      )}

      {showWordmark && (
        <span
          style={{
            fontWeight: 900,
            fontSize: cfg.wordmarkFontSize,
            letterSpacing: '-0.04em',
            lineHeight: 1,
            display: 'inline-flex',
            alignItems: 'baseline',
          }}
        >
          <span style={{ color: '#ffffff' }}>Data</span>
          <span style={{ color: '#3b82f6' }}>Pulse</span>
        </span>
      )}

      {showPulse && (
        <PulseBar
          color="blue"
          width={cfg.pulseWidth}
          height={cfg.pulseHeight}
          animate={animate}
        />
      )}

      {withHalo && (
        <div
          aria-hidden
          style={{
            position: 'absolute',
            left: '8%',
            right: '8%',
            bottom: 0,
            height: 1,
            background:
              'linear-gradient(90deg, transparent, rgba(59, 130, 246, 0.6), transparent)',
            opacity: 0.5,
          }}
        />
      )}
    </div>
  )
}
