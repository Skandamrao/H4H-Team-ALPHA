import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Send,
  FileText,
  AlertTriangle,
  HelpCircle,
  Loader2,
  Copy,
  Check,
  Sparkles,
  Bot,
  User,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { askAssistant, getAssistantSuggestions, type AssistantAnswer } from '@/lib/api'
import PageHeader from '@/components/PageHeader'
import { cn } from '@/lib/utils'

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const map: Record<string, string> = {
    High: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    Medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    Low: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    Insufficient: 'bg-red-500/20 text-red-400 border-red-500/30',
  }
  return (
    <span
      className={cn(
        'px-2.5 py-0.5 rounded-full text-xs font-medium border flex items-center gap-1.5',
        map[confidence] || map.Low
      )}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      Confidence: {confidence}
    </span>
  )
}

interface MessageItem {
  id: string
  question: string
  answer: AssistantAnswer
  timestamp: string
}

export default function AIAssistant() {
  const [searchParams] = useSearchParams()
  const initialQuery = searchParams.get('q') || ''

  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<MessageItem[]>([])
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [expandedEvidence, setExpandedEvidence] = useState<Record<string, boolean>>({})

  const bottomRef = useRef<HTMLDivElement>(null)

  const { data: suggestions } = useQuery({
    queryKey: ['suggestions'],
    queryFn: getAssistantSuggestions,
  })

  const askMutation = useMutation({
    mutationFn: (q: string) => askAssistant(q),
    onSuccess: (data, variables) => {
      const newItem: MessageItem = {
        id: `msg-${Date.now()}`,
        question: variables,
        answer: data,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }
      setMessages((prev) => [newItem, ...prev])
      setQuestion('')
      setTimeout(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    },
  })

  useEffect(() => {
    if (initialQuery && initialQuery.trim()) {
      setQuestion(initialQuery)
      askMutation.mutate(initialQuery.trim())
    }
  }, [initialQuery])

  const handleAsk = () => {
    if (!question.trim() || askMutation.isPending) return
    askMutation.mutate(question.trim())
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleAsk()
    }
  }

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const toggleEvidence = (id: string) => {
    setExpandedEvidence((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  return (
    <div className="px-6 py-6 space-y-6 max-w-5xl mx-auto">
      <PageHeader
        title="AI Historical Assistant"
        subtitle="Natural language queries verified strictly against project records — with citations, timestamps, and conflict warnings"
      />

      {/* Input Box */}
      <div className="rounded-xl border border-purple-500/30 bg-[#0d1530]/90 p-4 shadow-xl backdrop-blur-md">
        <div className="flex gap-3">
          <div className="relative flex-1">
            <textarea
              className="w-full bg-[#070b19] border border-slate-700/60 rounded-xl px-4 py-3.5 text-sm text-slate-100 placeholder-slate-500 resize-none focus:outline-none focus:border-purple-500/70 focus:ring-1 focus:ring-purple-500/40 transition-all font-sans leading-relaxed"
              placeholder="Ask any historical or architectural question… e.g. Why was Google Login renamed to Google Authentication?"
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={askMutation.isPending}
            />
            <div className="absolute right-3 bottom-3 text-[11px] text-slate-500 hidden sm:block">
              Press Enter to ask • Shift+Enter for newline
            </div>
          </div>
          <button
            className="px-5 py-3 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-medium text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50 self-end shadow-md shadow-purple-900/30 h-12"
            onClick={handleAsk}
            disabled={askMutation.isPending || !question.trim()}
          >
            {askMutation.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Send size={16} />
            )}
            <span className="hidden sm:inline">Verify & Ask</span>
          </button>
        </div>

        {/* Suggested Queries Chips */}
        {suggestions?.suggestions && (
          <div className="mt-3 pt-3 border-t border-slate-800/80 flex items-center gap-2 flex-wrap text-xs">
            <span className="text-slate-400 font-medium flex items-center gap-1">
              <Sparkles size={12} className="text-purple-400" />
              Suggested:
            </span>
            {suggestions.suggestions.slice(0, 4).map((s, i) => (
              <button
                key={i}
                className="px-2.5 py-1 rounded-lg text-xs bg-slate-900/80 hover:bg-purple-950/40 text-slate-300 hover:text-purple-200 border border-slate-800 hover:border-purple-600/40 transition-all text-left truncate max-w-xs"
                onClick={() => {
                  setQuestion(s)
                  askMutation.mutate(s)
                }}
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Loading state indicator */}
      {askMutation.isPending && (
        <div className="rounded-xl border border-purple-500/30 bg-[#0d1530]/80 p-6 text-center text-slate-400 space-y-3 shadow-lg animate-pulse">
          <div className="flex items-center justify-center gap-2 text-purple-300 font-medium text-sm">
            <Loader2 size={18} className="animate-spin text-purple-400" />
            <span>Consulting temporal graph & verifying citations…</span>
          </div>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Extracting relevant chronological events, scoring keyword proximity, and validating
            supporting document excerpts.
          </p>
        </div>
      )}

      {/* Conversation Thread / Answers */}
      <div className="space-y-6">
        {messages.map((item) => {
          const ans = item.answer
          const isEvidenceOpen = expandedEvidence[item.id] ?? true

          return (
            <div
              key={item.id}
              className="rounded-xl border border-purple-900/30 bg-[#0d1530]/90 p-6 space-y-5 shadow-xl transition-all duration-200 hover:border-purple-500/40"
            >
              {/* Question Header */}
              <div className="flex items-start justify-between gap-3 border-b border-slate-800/80 pb-4">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-purple-600/20 text-purple-300 border border-purple-500/30 mt-0.5">
                    <User size={15} />
                  </div>
                  <div>
                    <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">
                      Question asked at {item.timestamp}
                    </div>
                    <h3 className="text-base text-white font-semibold mt-0.5">{item.question}</h3>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => copyToClipboard(ans.answer, item.id)}
                    className="p-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 text-slate-400 hover:text-white border border-slate-700/50 transition-colors text-xs flex items-center gap-1"
                    title="Copy Answer"
                  >
                    {copiedId === item.id ? (
                      <Check size={13} className="text-emerald-400" />
                    ) : (
                      <Copy size={13} />
                    )}
                    <span className="hidden sm:inline">
                      {copiedId === item.id ? 'Copied' : 'Copy'}
                    </span>
                  </button>
                </div>
              </div>

              {/* Verified Answer Narrative */}
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-emerald-600/20 text-emerald-300 border border-emerald-500/30 mt-0.5 flex-shrink-0">
                  <Bot size={15} />
                </div>
                <div className="flex-1 space-y-3">
                  <div className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap font-sans">
                    {ans.answer}
                  </div>

                  {/* Historical Milestones List */}
                  {ans.historical_events.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-slate-800/60">
                      <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                        Key Historical Milestones
                      </div>
                      <div className="grid grid-cols-1 gap-2">
                        {ans.historical_events.map((e, idx) => (
                          <div
                            key={idx}
                            className="flex items-start gap-3 p-2 rounded-lg bg-slate-900/60 border border-slate-800/70 text-xs"
                          >
                            <span className="font-mono text-purple-300 font-medium whitespace-nowrap bg-purple-950/40 px-2 py-0.5 rounded border border-purple-800/30 text-[11px]">
                              {e.date}
                            </span>
                            <span className="text-slate-300">{e.description}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Supporting Evidence Citations */}
                  {ans.supporting_evidence.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-slate-800/60">
                      <button
                        onClick={() => toggleEvidence(item.id)}
                        className="flex items-center justify-between w-full text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200 transition-colors py-1"
                      >
                        <span className="flex items-center gap-1.5">
                          <FileText size={13} className="text-amber-400" />
                          Supporting Evidence Citations ({ans.supporting_evidence.length})
                        </span>
                        {isEvidenceOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>

                      {isEvidenceOpen && (
                        <div className="mt-2 space-y-2">
                          {ans.supporting_evidence.map((ev, idx) => (
                            <div
                              key={idx}
                              className="p-3 rounded-lg bg-slate-900/70 border border-amber-500/20 text-xs space-y-1.5"
                            >
                              <div className="flex items-center justify-between text-amber-300 font-medium">
                                <span className="font-mono text-[11px] truncate max-w-md">
                                  📄 {ev.document_filename}
                                </span>
                              </div>
                              {ev.excerpt && (
                                <blockquote className="text-slate-400 font-mono text-[11px] italic pl-2 border-l-2 border-amber-500/40 leading-relaxed">
                                  "{ev.excerpt}"
                                </blockquote>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Conflict Notice */}
                  {ans.has_conflicts && ans.conflict_note && (
                    <div className="rounded-lg border border-red-500/40 bg-red-950/20 p-3.5 space-y-1">
                      <div className="flex items-center gap-2 text-red-400 text-xs font-semibold uppercase tracking-wider">
                        <AlertTriangle size={14} />
                        Historical Inconsistency Flagged
                      </div>
                      <div className="text-xs text-red-200 leading-relaxed font-sans">
                        {ans.conflict_note}
                      </div>
                    </div>
                  )}

                  {/* Missing Info Notice */}
                  {ans.missing_information && (
                    <div className="rounded-lg border border-yellow-500/40 bg-yellow-950/20 p-3.5 space-y-1">
                      <div className="flex items-center gap-2 text-yellow-400 text-xs font-semibold uppercase tracking-wider">
                        <HelpCircle size={14} />
                        Information Gap in Records
                      </div>
                      <div className="text-xs text-yellow-200 leading-relaxed font-sans">
                        {ans.missing_information}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Footer Verification Bar */}
              <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-500">
                <ConfidenceBadge confidence={ans.confidence} />
                <span className="text-[11px] font-mono">
                  Grounding: 100% database verified excerpts
                </span>
              </div>
            </div>
          )
        })}
      </div>

      <div ref={bottomRef} />
    </div>
  )
}
