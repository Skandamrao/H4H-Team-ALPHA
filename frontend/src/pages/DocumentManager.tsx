import { useState, useCallback, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Upload,
  FileText,
  CheckCircle,
  AlertCircle,
  Clock,
  RefreshCw,
  Sparkles,
  BrainCircuit,
  Trash2,
  Loader2,
} from 'lucide-react'
import {
  getDocuments,
  uploadDocuments,
  loadSampleData,
  reprocessDocuments,
  deleteDocument,
  type Document,
} from '@/lib/api'
import PageHeader from '@/components/PageHeader'
import { formatDateTime, formatFileSize, cn } from '@/lib/utils'

function StatusIcon({ status }: { status: string }) {
  if (status === 'COMPLETED') return <CheckCircle size={14} className="text-green-400" />
  if (status === 'FAILED') return <AlertCircle size={14} className="text-red-400" />
  return <Clock size={14} className="text-yellow-400" />
}

export default function DocumentManager() {
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  // Track per-file batch progress for ultra-fast responsive uploads
  const [uploadProgress, setUploadProgress] = useState<{
    current: number
    total: number
    currentFilename: string
    isUploading: boolean
    errorMessage?: string
    successMessage?: string
  }>({
    current: 0,
    total: 0,
    currentFilename: '',
    isUploading: false,
  })

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['documents'],
    queryFn: () => getDocuments(),
  })

  const loadSampleMutation = useMutation({
    mutationFn: () => loadSampleData(),
    onSuccess: () => {
      queryClient.invalidateQueries()
    },
  })

  const reprocessMutation = useMutation({
    mutationFn: () => reprocessDocuments(),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
      queryClient.invalidateQueries({ queryKey: ['features'] })
      queryClient.invalidateQueries({ queryKey: ['events'] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-graph'] })
      alert(`Reprocessing complete: ${data.events_extracted} events extracted from ${data.documents_reprocessed} documents.`)
    },
    onError: () => {
      alert('Reprocessing failed. Check that the backend is running and Groq API key is configured.')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (documentId: string) => deleteDocument(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
      queryClient.invalidateQueries({ queryKey: ['features'] })
      queryClient.invalidateQueries({ queryKey: ['events'] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-graph'] })
      queryClient.invalidateQueries({ queryKey: ['timeline'] })
    },
    onError: (err: any) => {
      alert(`Failed to delete document: ${err.response?.data?.detail || err.message || 'Unknown error'}`)
    },
  })

  const handleDelete = (doc: Document) => {
    if (
      window.confirm(
        `Are you sure you want to delete "${doc.original_filename}"?\n\nThis will permanently delete the document and all its associated events and evidence from the knowledge graph.`
      )
    ) {
      deleteMutation.mutate(doc.id)
    }
  }

  // Fast sequential/concurrent file pipeline with immediate table updates
  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return
      const fileArray = Array.from(files)

      setUploadProgress({
        current: 0,
        total: fileArray.length,
        currentFilename: fileArray[0].name,
        isUploading: true,
        errorMessage: undefined,
        successMessage: undefined,
      })

      let completed = 0
      let lastError = ''

      for (let i = 0; i < fileArray.length; i++) {
        const file = fileArray[i]
        setUploadProgress((prev) => ({
          ...prev,
          current: i + 1,
          currentFilename: file.name,
        }))

        try {
          // Process file and update document table immediately
          await uploadDocuments([file])
          completed++
          queryClient.invalidateQueries({ queryKey: ['documents'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
        } catch (err: any) {
          lastError =
            err?.response?.data?.detail || err?.message || `Failed to process ${file.name}`
        }
      }

      // Final synchronization of all connected queries
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
      queryClient.invalidateQueries({ queryKey: ['features'] })
      queryClient.invalidateQueries({ queryKey: ['events'] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-graph'] })

      setUploadProgress((prev) => ({
        ...prev,
        isUploading: false,
        successMessage:
          completed > 0
            ? `Successfully uploaded ${completed} of ${fileArray.length} document(s).`
            : undefined,
        errorMessage: lastError || undefined,
      }))
    },
    [queryClient]
  )

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleFiles(e.dataTransfer.files)
  }

  const uploadPct =
    uploadProgress.total > 0
      ? Math.round((uploadProgress.current / uploadProgress.total) * 100)
      : 0

  return (
    <div className="px-6 py-6 space-y-6">
      <PageHeader
        title="Document Manager"
        subtitle="Fast multi-document upload, PyMuPDF extraction, and temporal record tracking"
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => reprocessMutation.mutate()}
              disabled={reprocessMutation.isPending || !data?.documents?.length}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-600/30 hover:bg-emerald-600/50 text-sm text-emerald-300 border border-emerald-500/30 transition-colors disabled:opacity-50"
              title="Run AI Event Extraction on all uploaded documents"
            >
              <BrainCircuit
                size={14}
                className={reprocessMutation.isPending ? 'animate-spin' : ''}
              />
              {reprocessMutation.isPending ? 'Extracting Events...' : 'Reprocess with AI'}
            </button>
            <button
              onClick={() => loadSampleMutation.mutate()}
              disabled={loadSampleMutation.isPending}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-purple-600/30 hover:bg-purple-600/50 text-sm text-purple-300 border border-purple-500/30 transition-colors disabled:opacity-50"
            >
              <Sparkles size={14} className={loadSampleMutation.isPending ? 'animate-spin' : ''} />
              {loadSampleMutation.isPending ? 'Loading Demo...' : 'Load Sample Data'}
            </button>
            <button
              onClick={() => refetch()}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm text-slate-300 transition-colors"
            >
              <RefreshCw size={14} />
              Refresh
            </button>
          </div>
        }
      />

      {/* Drop zone with Progress Bar */}
      <div
        className={cn(
          'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200 relative overflow-hidden',
          dragOver
            ? 'border-purple-400 bg-purple-900/20'
            : 'border-slate-700 hover:border-purple-600/50 bg-slate-800/20 hover:bg-slate-800/40'
        )}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !uploadProgress.isUploading && fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.txt,.md,.json"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <Upload size={32} className="mx-auto mb-3 text-slate-400" />
        <div className="text-white font-medium mb-1">
          {uploadProgress.isUploading
            ? `Uploading & Processing File ${uploadProgress.current} of ${uploadProgress.total}...`
            : 'Drop 1, 3, or more files here or click to upload'}
        </div>
        <div className="text-xs text-slate-400">
          Supports multiple PDF, TXT, Markdown, and JSON files simultaneously
        </div>

        {/* Live Determinate Progress Bar for multi-file upload */}
        {uploadProgress.isUploading && (
          <div className="mt-4 max-w-md mx-auto space-y-2">
            <div className="flex items-center justify-between text-xs text-purple-300 font-mono">
              <span className="truncate max-w-[250px]">Processing: {uploadProgress.currentFilename}</span>
              <span>{uploadPct}%</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden border border-purple-900/50">
              <div
                className="bg-gradient-to-r from-purple-500 to-indigo-400 h-2 rounded-full transition-all duration-300"
                style={{ width: `${uploadPct}%` }}
              />
            </div>
          </div>
        )}

        {/* Success message */}
        {uploadProgress.successMessage && !uploadProgress.isUploading && (
          <div className="mt-3 text-xs text-emerald-400 flex items-center justify-center gap-1.5 font-medium">
            <CheckCircle size={14} /> {uploadProgress.successMessage}
          </div>
        )}

        {/* Error message */}
        {uploadProgress.errorMessage && !uploadProgress.isUploading && (
          <div className="mt-3 text-xs text-red-400 font-medium">
            {uploadProgress.errorMessage}
          </div>
        )}
      </div>

      {/* Documents table */}
      <div className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 overflow-hidden shadow-lg">
        <div className="px-5 py-3 border-b border-slate-800/50 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            {data?.total ?? 0} Ingested Document{(data?.total ?? 0) !== 1 ? 's' : ''}
          </span>
          <span className="text-[11px] font-mono text-slate-500">
            SHA-256 Verified • Deduplicated
          </span>
        </div>
        {isLoading ? (
          <div className="p-8 text-center text-slate-500 text-xs">Loading documents…</div>
        ) : !data?.documents.length ? (
          <div className="p-8 text-center text-slate-500 text-xs">No documents uploaded yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 border-b border-slate-800/50 bg-slate-900/30">
                <th className="px-5 py-3 text-left font-medium">Filename</th>
                <th className="px-4 py-3 text-left font-medium">Type</th>
                <th className="px-4 py-3 text-left font-medium">Size</th>
                <th className="px-4 py-3 text-left font-medium">Doc Date</th>
                <th className="px-4 py-3 text-left font-medium">Ingested</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Events</th>
                <th className="px-4 py-3 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {data.documents.map((doc) => (
                <tr
                  key={doc.id}
                  className="border-b border-slate-800/30 hover:bg-slate-800/20 transition-colors"
                >
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <FileText size={14} className="text-purple-400 flex-shrink-0" />
                      <span className="text-slate-200 truncate max-w-xs font-medium">
                        {doc.original_filename}
                      </span>
                      {doc.is_duplicate && (
                        <span className="px-1.5 py-0.5 text-[10px] rounded bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 font-semibold uppercase">
                          duplicate
                        </span>
                      )}
                    </div>
                    {doc.processing_error && (
                      <div className="text-xs text-red-400 mt-0.5 truncate max-w-sm">
                        {doc.processing_error}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-400 uppercase text-xs font-mono">
                    {doc.file_type}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs font-mono">
                    {formatFileSize(doc.file_size_bytes)}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {doc.document_date ? (
                      formatDateTime(doc.document_date)
                    ) : (
                      <span className="text-slate-600 italic">unknown</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {formatDateTime(doc.ingested_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <StatusIcon status={doc.processing_status} />
                      <span
                        className={cn(
                          'text-xs font-medium',
                          doc.processing_status === 'COMPLETED'
                            ? 'text-green-400'
                            : doc.processing_status === 'FAILED'
                            ? 'text-red-400'
                            : 'text-yellow-400'
                        )}
                      >
                        {doc.processing_status}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-purple-400 font-mono font-semibold text-xs">
                    {doc.event_count}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleDelete(doc)}
                      disabled={deleteMutation.isPending && deleteMutation.variables === doc.id}
                      className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 border border-transparent hover:border-red-500/30 transition-all disabled:opacity-40 inline-flex items-center justify-center"
                      title={`Delete ${doc.original_filename}`}
                    >
                      {deleteMutation.isPending && deleteMutation.variables === doc.id ? (
                        <Loader2 size={14} className="animate-spin text-red-400" />
                      ) : (
                        <Trash2 size={14} />
                      )}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
