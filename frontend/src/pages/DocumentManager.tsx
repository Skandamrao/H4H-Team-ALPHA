import { useState, useCallback, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, FileText, CheckCircle, AlertCircle, Clock, RefreshCw, Sparkles, BrainCircuit, Trash2, Loader2 } from 'lucide-react'
import { getDocuments, uploadDocuments, loadSampleData, reprocessDocuments, deleteDocument, type Document } from '@/lib/api'
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

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['documents'],
    queryFn: () => getDocuments(),
  })

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => uploadDocuments(files),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
      queryClient.invalidateQueries({ queryKey: ['features'] })
      queryClient.invalidateQueries({ queryKey: ['events'] })
      queryClient.invalidateQueries({ queryKey: ['knowledge-graph'] })
    },
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
    if (window.confirm(`Are you sure you want to delete "${doc.original_filename}"?\n\nThis will permanently delete the document and all its associated events and evidence from the knowledge graph.`)) {
      deleteMutation.mutate(doc.id)
    }
  }

  const handleFiles = useCallback((files: FileList | null) => {
    if (!files || files.length === 0) return
    const fileArray = Array.from(files)
    uploadMutation.mutate(fileArray)
  }, [uploadMutation])

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleFiles(e.dataTransfer.files)
  }

  return (
    <div className="px-6 py-6 space-y-6">
      <PageHeader
        title="Document Manager"
        subtitle="Upload and manage project documents for historical analysis"
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => reprocessMutation.mutate()}
              disabled={reprocessMutation.isPending || !data?.documents?.length}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-600/30 hover:bg-emerald-600/50 text-sm text-emerald-300 border border-emerald-500/30 transition-colors disabled:opacity-50"
              title="Run AI Event Extraction on all uploaded documents"
            >
              <BrainCircuit size={14} className={reprocessMutation.isPending ? 'animate-spin' : ''} />
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

      {/* Drop zone */}
      <div
        className={cn(
          'border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all duration-200',
          dragOver
            ? 'border-purple-400 bg-purple-900/20'
            : 'border-slate-700 hover:border-purple-600/50 bg-slate-800/20 hover:bg-slate-800/40'
        )}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.txt,.md,.json"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <Upload size={32} className="mx-auto mb-3 text-slate-500" />
        <div className="text-white font-medium mb-1">Drop files here or click to upload</div>
        <div className="text-sm text-slate-500">Supports PDF, TXT, Markdown, JSON (max 50 MB each)</div>
        {uploadMutation.isPending && (
          <div className="mt-3 text-sm text-purple-400 animate-pulse">Processing documents & extracting events with Groq AI…</div>
        )}
        {uploadMutation.isSuccess && (
          <div className="mt-3 text-sm text-emerald-400 flex items-center justify-center gap-1.5">
            <CheckCircle size={14} /> Documents uploaded and processed successfully.
          </div>
        )}
        {uploadMutation.isError && (
          <div className="mt-3 text-sm text-red-400">
            {(uploadMutation.error as any)?.response?.data?.detail ||
             (uploadMutation.error as any)?.message ||
             'Upload failed. Check backend connection.'}
          </div>
        )}
      </div>

      {/* Documents table */}
      <div className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-800/50 flex items-center justify-between">
          <span className="text-sm font-medium text-slate-300">
            {data?.total ?? 0} document{(data?.total ?? 0) !== 1 ? 's' : ''}
          </span>
        </div>
        {isLoading ? (
          <div className="p-8 text-center text-slate-500">Loading…</div>
        ) : !data?.documents.length ? (
          <div className="p-8 text-center text-slate-500">No documents uploaded yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 border-b border-slate-800/50">
                <th className="px-5 py-3 text-left">Filename</th>
                <th className="px-4 py-3 text-left">Type</th>
                <th className="px-4 py-3 text-left">Size</th>
                <th className="px-4 py-3 text-left">Doc Date</th>
                <th className="px-4 py-3 text-left">Ingested</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Events</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {data.documents.map((doc) => (
                <tr key={doc.id} className="border-b border-slate-800/30 hover:bg-slate-800/20 transition-colors">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <FileText size={14} className="text-slate-500 flex-shrink-0" />
                      <span className="text-slate-200 truncate max-w-xs">{doc.original_filename}</span>
                      {doc.is_duplicate && (
                        <span className="px-1.5 py-0.5 text-xs rounded bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
                          duplicate
                        </span>
                      )}
                    </div>
                    {doc.processing_error && (
                      <div className="text-xs text-red-400 mt-0.5 truncate max-w-sm">{doc.processing_error}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-400 uppercase text-xs">{doc.file_type}</td>
                  <td className="px-4 py-3 text-slate-400">{formatFileSize(doc.file_size_bytes)}</td>
                  <td className="px-4 py-3 text-slate-400">
                    {doc.document_date ? formatDateTime(doc.document_date) : (
                      <span className="text-slate-600 italic">unknown</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-400">{formatDateTime(doc.ingested_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <StatusIcon status={doc.processing_status} />
                      <span className={cn(
                        'text-xs',
                        doc.processing_status === 'COMPLETED' ? 'text-green-400' :
                        doc.processing_status === 'FAILED' ? 'text-red-400' : 'text-yellow-400'
                      )}>{doc.processing_status}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-purple-400 font-medium">{doc.event_count}</td>
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

