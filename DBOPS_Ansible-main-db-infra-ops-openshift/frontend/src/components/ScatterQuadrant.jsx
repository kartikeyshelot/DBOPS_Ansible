import React from 'react'
import Plot from 'react-plotly.js'

const COLORS = {
  URGENT: '#ef4444', HIGH: '#f97316', MEDIUM: '#3b82f6', LOW: '#10b981', NONE: '#94a3b8',
}

export default function ScatterQuadrant({ servers, onServerClick }) {
  if (!servers || servers.length === 0) return null

  const priorities = ['URGENT', 'HIGH', 'MEDIUM', 'LOW', 'NONE']
  const traces = priorities
    .map(pri => {
      const subset = servers.filter(s => s.priority === pri)
      if (subset.length === 0) return null
      return {
        x: subset.map(s => s.current_load),
        y: subset.map(s => Math.max(s.total_alerts, 0.5)),
        text: subset.map(s => s.name),
        customdata: subset,
        name: pri,
        mode: 'markers',
        type: 'scatter',
        marker: {
          color: COLORS[pri],
          size: subset.map(s => Math.max(10, Math.min(s.total_alerts * 2, 50))),
          opacity: 0.75,
          line: { width: 1.5, color: 'rgba(255,255,255,0.8)' },
        },
        hovertemplate: '<b>%{text}</b><br>Load: %{x:.1f}%<br>Alerts: %{y}<extra></extra>',
      }
    })
    .filter(Boolean)

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      <div style={{ padding: '16px 20px 0' }}>
        <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Risk Quadrant</h4>
        <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
          Load vs alerts — click any server to drill down
        </p>
      </div>
      <Plot
        data={traces}
        layout={{
          height: 380,
          margin: { t: 16, b: 48, l: 56, r: 16 },
          paper_bgcolor: 'transparent',
          plot_bgcolor: 'transparent',
          font: { family: 'Plus Jakarta Sans', color: '#64748b', size: 11 },
          xaxis: {
            title: { text: 'Resource Load (%)', font: { size: 11 } },
            range: [-5, 105],
            gridcolor: '#f1f5f9', zerolinecolor: '#e2e8f0',
          },
          yaxis: {
            title: { text: 'Active Alerts', font: { size: 11 } },
            type: 'log', range: [-0.5, 2.5],
            gridcolor: '#f1f5f9', zerolinecolor: '#e2e8f0',
          },
          shapes: [
            { type: 'line', x0: 70, x1: 70, y0: 0, y1: 1, yref: 'paper',
              line: { dash: 'dot', color: '#e2e8f0', width: 1.5 }},
            { type: 'line', y0: 5, y1: 5, x0: 0, x1: 1, xref: 'paper',
              line: { dash: 'dot', color: '#e2e8f0', width: 1.5 }},
          ],
          annotations: [
            { x: 88, y: 0.7, text: 'Silent Fail', showarrow: false, font: { size: 10, color: '#94a3b8' }},
            { x: 88, y: 50, text: 'Critical', showarrow: false, font: { size: 10, color: '#ef4444' }},
            { x: 12, y: 50, text: 'Alert Storm', showarrow: false, font: { size: 10, color: '#f97316' }},
            { x: 12, y: 0.7, text: 'Healthy', showarrow: false, font: { size: 10, color: '#10b981' }},
          ],
          legend: { orientation: 'h', yanchor: 'bottom', y: 1.04, xanchor: 'right', x: 1, font: { size: 11 } },
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%' }}
        onClick={(e) => {
          if (e.points?.[0]?.customdata && onServerClick) {
            onServerClick(e.points[0].customdata)
          }
        }}
      />
    </div>
  )
}
