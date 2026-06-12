import { useState, useRef } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { Button } from './ui/Button'
import { Dialog } from './ui/Dialog'
import { downloadTenantDataExport, importTenantData } from '../api'

export default function ExportImport() {
  // Export state
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState(null)
  const [exportFormat, setExportFormat] = useState('zip')

  // Import state
  const [selectedFile, setSelectedFile] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [dryRunResult, setDryRunResult] = useState(null)
  const [dryRunLoading, setDryRunLoading] = useState(false)
  const [dryRunError, setDryRunError] = useState(null)
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const [importError, setImportError] = useState(null)

  const fileInputRef = useRef(null)

  const handleExport = async () => {
    setExporting(true)
    setExportError(null)
    try {
      await downloadTenantDataExport(exportFormat)
    } catch (e) {
      setExportError(e.message)
    } finally {
      setExporting(false)
    }
  }

  const handleFileSelect = (file) => {
    if (!file) return
    if (!file.name.endsWith('.zip')) {
      setDryRunError('Nur ZIP-Dateien werden akzeptiert.')
      return
    }
    if (file.size > 100 * 1024 * 1024) {
      setDryRunError('Datei zu groß (max. 100 MB).')
      return
    }
    setSelectedFile(file)
    setDryRunResult(null)
    setDryRunError(null)
    setImportResult(null)
    setImportError(null)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    handleFileSelect(file)
  }

  const handleDryRun = async () => {
    if (!selectedFile) return
    setDryRunLoading(true)
    setDryRunError(null)
    setDryRunResult(null)
    try {
      const result = await importTenantData(selectedFile, true, true)
      setDryRunResult(result)
      if (result.valid) {
        setShowConfirmModal(true)
      }
    } catch (e) {
      setDryRunError(e.message)
    } finally {
      setDryRunLoading(false)
    }
  }

  const handleConfirmImport = async () => {
    setShowConfirmModal(false)
    setImporting(true)
    setImportError(null)
    try {
      const result = await importTenantData(selectedFile, false, true)
      setImportResult(result)
      setSelectedFile(null)
      setDryRunResult(null)
    } catch (e) {
      setImportError(e.message)
    } finally {
      setImporting(false)
    }
  }

  const resetImport = () => {
    setSelectedFile(null)
    setDryRunResult(null)
    setDryRunError(null)
    setImportResult(null)
    setImportError(null)
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Daten & Export</h2>

      {/* Export */}
      <Card>
        <CardHeader>
          <CardTitle>Daten exportieren</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Exportiert alle Tenant-Daten (Quellen, Items, Content, Einstellungen). Die Datei kann
            als Backup oder zur Migration genutzt werden.
          </p>

          {/* Format-Selector */}
          <div className="space-y-2">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Format</p>
            <div className="flex flex-wrap gap-3">
              {[
                { value: 'zip', label: 'ZIP (JSON)', desc: 'Vollständiger JSON-Export' },
                { value: 'excel', label: 'Excel (.xlsx)', desc: 'Tabellen als Excel-Sheets' },
                { value: 'csv', label: 'CSV', desc: 'Komma-getrennte Tabellen' },
                { value: 'all', label: 'Alle Formate', desc: 'JSON + Excel + CSV kombiniert' },
              ].map((opt) => (
                <label
                  key={opt.value}
                  className={`flex items-start gap-2 p-3 rounded-lg border cursor-pointer transition-colors
                    ${
                      exportFormat === opt.value
                        ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                        : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                    }`}
                >
                  <input
                    type="radio"
                    name="exportFormat"
                    value={opt.value}
                    checked={exportFormat === opt.value}
                    onChange={() => setExportFormat(opt.value)}
                    className="mt-0.5 accent-primary-500"
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                      {opt.label}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{opt.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {exportError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-300">
              Fehler: {exportError}
            </div>
          )}

          <div className="flex items-center gap-3">
            <Button onClick={handleExport} disabled={exporting}>
              {exporting ? 'Exportiere...' : 'Daten exportieren'}
            </Button>
            {exporting && (
              <span className="text-sm text-gray-500 dark:text-gray-400 animate-pulse">
                Download wird vorbereitet...
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Import */}
      <Card>
        <CardHeader>
          <CardTitle>Daten importieren</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Importiert Tenant-Daten aus einer zuvor exportierten ZIP-Datei. Maximale Dateigröße: 100
            MB.
          </p>

          {importResult ? (
            <div className="space-y-3">
              <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                <p className="font-medium text-green-800 dark:text-green-200 text-sm">
                  Import erfolgreich
                </p>
                {importResult.imported_counts && (
                  <ul className="mt-2 space-y-1 text-sm text-green-700 dark:text-green-300">
                    {Object.entries(importResult.imported_counts).map(([key, val]) => (
                      <li key={key}>
                        {key}: {val} importiert
                      </li>
                    ))}
                  </ul>
                )}
                {importResult.message && (
                  <p className="mt-2 text-sm text-green-700 dark:text-green-300">
                    {importResult.message}
                  </p>
                )}
              </div>
              <Button variant="secondary" onClick={resetImport}>
                Neuen Import starten
              </Button>
            </div>
          ) : (
            <>
              {/* Drop zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOver(true)
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors
                  ${
                    dragOver
                      ? 'border-primary-400 bg-primary-50 dark:bg-primary-900/20'
                      : 'border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500 bg-gray-50 dark:bg-gray-800/50'
                  }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={(e) => handleFileSelect(e.target.files[0])}
                />
                {selectedFile ? (
                  <div className="space-y-1">
                    <p className="font-medium text-gray-700 dark:text-gray-300 text-sm">
                      {selectedFile.name}
                    </p>
                    <p className="text-xs text-gray-500">
                      {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                      ZIP-Datei hier ablegen oder klicken
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">max. 100 MB</p>
                  </div>
                )}
              </div>

              {dryRunError && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-300">
                  Fehler: {dryRunError}
                </div>
              )}

              {importError && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-300">
                  Import-Fehler: {importError}
                </div>
              )}

              {dryRunResult && !dryRunResult.valid && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 space-y-2">
                  <p className="font-medium text-red-800 dark:text-red-200 text-sm">
                    ZIP-Datei ungültig
                  </p>
                  {dryRunResult.errors && (
                    <ul className="text-sm text-red-700 dark:text-red-300 list-disc list-inside space-y-1">
                      {dryRunResult.errors.map((err, i) => (
                        <li key={i}>{err}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {dryRunResult?.valid && (
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 space-y-2">
                  <p className="font-medium text-blue-800 dark:text-blue-200 text-sm">
                    Vorschau (Dry-Run)
                  </p>
                  {dryRunResult.preview && (
                    <ul className="text-sm text-blue-700 dark:text-blue-300 space-y-1">
                      {Object.entries(dryRunResult.preview).map(([key, val]) => (
                        <li key={key}>
                          {key}: {typeof val === 'object' ? JSON.stringify(val) : val}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <div className="flex gap-3">
                {selectedFile && !dryRunResult?.valid && (
                  <Button onClick={handleDryRun} disabled={dryRunLoading || importing}>
                    {dryRunLoading ? 'Prüfe...' : 'Datei prüfen & Vorschau'}
                  </Button>
                )}
                {dryRunResult?.valid && (
                  <Button onClick={() => setShowConfirmModal(true)} disabled={importing}>
                    {importing ? 'Importiere...' : 'Import bestätigen'}
                  </Button>
                )}
                {selectedFile && (
                  <Button variant="secondary" onClick={resetImport}>
                    Zurücksetzen
                  </Button>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Confirm modal */}
      <Dialog
        open={showConfirmModal}
        onClose={() => setShowConfirmModal(false)}
        title="Import bestätigen"
      >
        <div className="space-y-4">
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
            <p className="font-medium text-amber-800 dark:text-amber-200 text-sm">Warnung</p>
            <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
              Der Import merged bestehende Daten mit den importierten Daten. Bestehende Einträge
              können überschrieben werden. Diese Aktion kann nicht rückgängig gemacht werden.
            </p>
          </div>

          {dryRunResult?.preview && (
            <div className="space-y-1">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Was wird importiert:
              </p>
              <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                {Object.entries(dryRunResult.preview).map(([key, val]) => (
                  <li key={key} className="flex justify-between">
                    <span>{key}</span>
                    <span className="font-medium">
                      {typeof val === 'object' ? JSON.stringify(val) : val}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <Button onClick={handleConfirmImport}>Ja, jetzt importieren</Button>
            <Button variant="secondary" onClick={() => setShowConfirmModal(false)}>
              Abbrechen
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
