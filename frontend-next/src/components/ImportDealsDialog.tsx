import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { Api } from '../api/client'
import type { DealImportSummary } from '../api/types'
import { importDeals, invalidateDeals } from '../deals'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'

export function ImportDealsDialog({ api }: { api: Api }) {
  const [isOpen, setIsOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [summary, setSummary] = useState<DealImportSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const reset = () => {
    setFile(null)
    setIsUploading(false)
    setSummary(null)
    setError(null)
  }

  const handleClose = () => {
    if (isUploading) return
    reset()
    setIsOpen(false)
  }

  const handleImport = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file || isUploading) return
    setIsUploading(true)
    setError(null)
    try {
      const res = await importDeals(api, file, 'lead_generation')
      setSummary(res)
      await Promise.all([
        invalidateDeals(queryClient),
        queryClient.invalidateQueries({ queryKey: ['organizations'] }),
      ])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <>
      <Button variant="quiet" onPress={() => setIsOpen(true)}>
        Import leads
      </Button>

      <Modal
        title="Import Deals"
        isOpen={isOpen}
        onOpenChange={(open) => !open && handleClose()}
      >
        {summary ? (
          <div className="quick-form">
            <p>
              <strong>Import completed!</strong>
            </p>
            <ul>
              <li>Deals created: {summary.imported_deals}</li>
              <li>Organizations created: {summary.created_organizations}</li>
              <li>Skipped duplicates: {summary.skipped_duplicates}</li>
            </ul>
            {summary.errors.length > 0 && (
              <div className="form-error">
                {summary.errors.map((err, i) => (
                  <p key={i}>{err}</p>
                ))}
              </div>
            )}
            <div className="form-actions">
              <Button onPress={handleClose}>Done</Button>
            </div>
          </div>
        ) : (
          <form className="quick-form" onSubmit={(e) => void handleImport(e)}>
            <p className="muted">
              Upload leads from CSV. Formatted for the <code>lead_generation</code> tool (e.g.{' '}
              <code>hot_leads.csv</code> with scores, entry angles, and company info).
            </p>

            <div style={{ margin: '1rem 0' }}>
              <input
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                disabled={isUploading}
                required
              />
            </div>

            {error && <p className="form-error">{error}</p>}

            <div className="form-actions">
              <Button variant="quiet" onPress={handleClose} isDisabled={isUploading}>
                Cancel
              </Button>
              <Button type="submit" isDisabled={!file || isUploading}>
                {isUploading ? 'Importing…' : 'Import'}
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </>
  )
}
