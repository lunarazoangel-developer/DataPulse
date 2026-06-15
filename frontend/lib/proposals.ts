import type { Proposal, ProposalRisk } from './api'

const RISK_ORDER: Record<ProposalRisk, number> = { high: 0, medium: 1, low: 2 }

export const RISK_META: Record<
  ProposalRisk,
  { label: string; color: string; ring: string; chip: string; bar: string }
> = {
  high: {
    label: 'Alto riesgo',
    color: 'text-status-red',
    ring: 'ring-status-red/40',
    chip: 'bg-status-red/15 border-status-red/40 text-status-red',
    bar: 'bg-status-red',
  },
  medium: {
    label: 'Riesgo medio',
    color: 'text-status-yellow',
    ring: 'ring-status-yellow/40',
    chip: 'bg-status-yellow/15 border-status-yellow/40 text-status-yellow',
    bar: 'bg-status-yellow',
  },
  low: {
    label: 'Bajo riesgo',
    color: 'text-status-green',
    ring: 'ring-status-green/40',
    chip: 'bg-status-green/15 border-status-green/40 text-status-green',
    bar: 'bg-status-green',
  },
}

export function sortByRisk(proposals: Proposal[]): Proposal[] {
  return [...proposals].sort((a, b) => RISK_ORDER[a.risk] - RISK_ORDER[b.risk])
}

export function isContinuar(text: string): boolean {
  return /^\s*continuar\s*$/i.test(text.trim())
}

export function defaultApprovals(proposals: Proposal[]): Record<string, boolean> {
  return Object.fromEntries(proposals.map(p => [p.id, true]))
}

export function countApproved(
  proposals: Proposal[],
  approvals: Record<string, boolean>
): number {
  return proposals.filter(p => approvals[p.id] !== false).length
}
