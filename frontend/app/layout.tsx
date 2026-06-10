import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'DataPulse',
  description: 'Intelligent Data Cleaning and Anomaly Detection',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
