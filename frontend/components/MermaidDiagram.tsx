'use client'

import { useEffect, useRef } from 'react'
import mermaid from 'mermaid'

interface MermaidDiagramProps {
  chart: string
}

export default function MermaidDiagram({ chart }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      er: {
        useMaxWidth: true,
        layoutDirection: 'TB',
        minEntityWidth: 100,
      }
    })
  }, [])

  useEffect(() => {
    if (!chart || !containerRef.current) return

    const renderChart = async () => {
      try {
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`
        const { svg } = await mermaid.render(id, chart)
        if (containerRef.current) {
          containerRef.current.innerHTML = svg
        }
      } catch (error) {
        console.error('Mermaid render error:', error)
        if (containerRef.current) {
          containerRef.current.innerHTML = `<pre class="text-status-red text-xs">${chart}</pre>`
        }
      }
    }

    renderChart()
  }, [chart])

  if (!chart) return null

  return (
    <div 
      ref={containerRef} 
      className="overflow-x-auto flex justify-center"
    />
  )
}
