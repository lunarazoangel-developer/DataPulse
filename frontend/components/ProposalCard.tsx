'use client'

import { useState } from 'react'
import { Check, X, Code2, ChevronDown, ChevronUp, Database } from 'lucide-react'
import type { Proposal } from '@/lib/api'
import { RISK_META } from '@/lib/proposals'

interface ProposalCardProps {
  proposal: Proposal
  approved: boolean
  onToggle: (id: string, approved: boolean) => void
}

function formatRows(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return n.toString()
}

export default function ProposalCard({ proposal, approved, onToggle }: ProposalCardProps) {
  const meta = RISK_META[proposal.risk] || RISK_META.medium
  const [showParams, setShowParams] = useState(false)
  const hasParams = proposal.params && Object.keys(proposal.params).length > 0
  const coverage = proposal.coverage_note
  const estimated = proposal.estimated_affected_rows

  return (
    <div
      className={`rounded-lg border border-border bg-bg-tertiary/60 overflow-hidden ring-1 ${meta.ring}`}
      data-testid={`proposal-${proposal.id}`}
    >
      <div className={`h-1 w-full ${meta.bar}`} />

      <div className="p-3 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span
                className={`text-[10px] uppercase tracking-widest font-semibold px-1.5 py-0.5 rounded border ${meta.chip}`}
              >
                {meta.label}
              </span>
              <span className="text-[10px] uppercase tracking-widest font-mono text-text-muted">
                {proposal.action}
              </span>
              {typeof estimated === 'number' && estimated > 0 && (
                <span
                  className="text-[10px] uppercase tracking-widest font-mono px-1.5 py-0.5 rounded border bg-bg-secondary border-border text-text-secondary"
                  title={coverage || `~${estimated} filas afectadas estimadas`}
                  data-testid={`proposal-coverage-${proposal.id}`}
                >
                  <Database className="w-3 h-3 inline-block mr-1 -mt-0.5" />
                  {coverage || `~${formatRows(estimated)} filas`}
                </span>
              )}
            </div>
            <h4 className="font-semibold text-sm text-text-primary break-words">
              {proposal.title}
            </h4>
          </div>
        </div>

        {proposal.description && (
          <p className="text-xs text-text-secondary leading-relaxed">
            {proposal.description}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono">
          {proposal.table && (
            <span className="px-1.5 py-0.5 rounded bg-bg-secondary text-text-secondary border border-border">
              {proposal.table}
            </span>
          )}
          {proposal.column && (
            <span className="px-1.5 py-0.5 rounded bg-bg-secondary text-accent border border-border">
              {proposal.column}
            </span>
          )}
        </div>

        {hasParams && (
          <div>
            <button
              type="button"
              onClick={() => setShowParams(v => !v)}
              className="flex items-center gap-1 text-[11px] text-text-muted hover:text-text-primary transition-colors"
            >
              <Code2 className="w-3 h-3" />
              params
              {showParams ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {showParams && (
              <pre className="mt-1 text-[11px] bg-bg-secondary border border-border rounded p-2 overflow-x-auto font-mono text-text-secondary">
                {JSON.stringify(proposal.params, null, 2)}
              </pre>
            )}
          </div>
        )}

        <div className="flex items-center gap-2 pt-1">
          <button
            type="button"
            onClick={() => onToggle(proposal.id, true)}
            aria-pressed={approved}
            title="Aprobar este cambio"
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded text-xs font-semibold border transition-all ${
              approved
                ? 'bg-status-green/20 border-status-green text-status-green ring-1 ring-status-green/40'
                : 'bg-bg-secondary border-border text-text-muted hover:border-status-green/40 hover:text-status-green'
            }`}
          >
            <Check className="w-4 h-4" />
            Aprobar
          </button>
          <button
            type="button"
            onClick={() => onToggle(proposal.id, false)}
            aria-pressed={!approved}
            title="Rechazar este cambio"
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded text-xs font-semibold border transition-all ${
              !approved
                ? 'bg-status-red/20 border-status-red text-status-red ring-1 ring-status-red/40'
                : 'bg-bg-secondary border-border text-text-muted hover:border-status-red/40 hover:text-status-red'
            }`}
          >
            <X className="w-4 h-4" />
            Rechazar
          </button>
        </div>
      </div>
    </div>
  )
}
