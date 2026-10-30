import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Send, FileText, AlertTriangle, HelpCircle, Loader2 } from 'lucide-react'
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
    <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium border', map[confidence] || map.Low)}>
      Confidence: {confidence}
    </span>
  )
}

export default function AIAssistant() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AssistantAnswer | null>(null)

  const { data: suggestions } = useQuery({
    queryKey: ['suggestions'],
    queryFn: getAssistantSuggestions,
  })

  const askMutation = useMutation({
    mutationFn: (q: string) => askAssistant(q),
    onSuccess: (data) => setAnswer(data),
  })

  const handleAsk = () => {
    if (!question.trim()) return
    askMutation.mutate(question.trim())
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleAsk()
    }
  }

  return (
    <div className="px-6 py-6 space-y-6">
      <PageHeader
        title="AI Historical Assistant"
        subtitle="Ask questions about your project's history — every answer is grounded in evidence"
      />

      {/* Suggestions */}
      {!answer && suggestions?.suggestions && (
        <div className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 p-5">
          <div className="text-sm font-medium text-slate-400 mb-3">Suggested questions</div>
          <div className="flex flex-wrap gap-2">
            {suggestions.suggestions.map((s, i) => (
              <button
                key={i}
                className="px-3 py-1.5 rounded-lg text-xs bg-slate-800/60 hover:bg-purple-900/30 text-slate-300 hover:text-purple-300 border border-slate-700/50 hover:border-purple-600/40 transition-all text-left"
                onClick={() => setQuestion(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 p-4">
        <div className="flex gap-3">
          <textarea
            className="flex-1 bg-slate-900/60 border border-slate-700/50 rounded-lg px-4 py-3 text-sm text-slate-200 placeholder-slate-500 resize-none focus:outline-none focus:border-purple-500/50 transition-colors"
            placeholder="Ask a historical question… e.g. Why was Google authentication introduced?"
            rows={3}
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button
            className="px-4 py-3 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-medium text-sm flex items-center gap-2 transition-colors disabled:opacity-50 self-end"
            onClick={handleAsk}
            disabled={askMutation.isPending || !question.trim()}
          >
            {askMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            Ask
          </button>
        </div>
      </div>

      {/* Loading state */}
      {askMutation.isPending && (
        <div className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 p-8 text-center text-slate-500 animate-pulse">
          Searching historical records and verifying evidence…
        </div>
      )}

      {/* Answer */}
      {answer && !askMutation.isPending && (
        <div className="rounded-xl border border-purple-900/30 bg-[#111b40]/80 p-6 space-y-5">
          {/* Question + clear button */}
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">Question</div>
              <div className="text-base text-white font-medium">{answer.question}</div>
            </div>
            <button
              onClick={() => { setAnswer(null); setQuestion('') }}
              className="flex-shrink-0 px-3 py-1.5 rounded-lg text-xs bg-slate-800/60 hover:bg-slate-700/60 text-slate-400 hover:text-slate-200 border border-slate-700/50 transition-colors whitespace-nowrap"
            >
              Ask another
            </button>
          </div>

          {/* Answer */}
          <div>
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">Answer</div>
            <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">{answer.answer}</div>
          </div>

          {/* Historical events */}
          {answer.historical_events.length > 0 && (
            <div>
              <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Historical Events</div>
              <div className="space-y-1.5">
                {answer.historical_events.map((e, i) => (
                  <div key={i} className="flex gap-3 text-sm">
                    <span className="font-mono text-purple-400 text-xs whitespace-nowrap mt-0.5">{e.date}</span>
                    <span className="text-slate-300">{e.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Evidence */}
          {answer.supporting_evidence.length > 0 && (
            <div>
              <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Supporting Evidence</div>
              <div className="space-y-2">
                {answer.supporting_evidence.map((ev, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <FileText size={13} className="text-slate-500 mt-0.5 flex-shrink-0" />
                    <div>
                      <div className="text-xs font-medium text-slate-300">{ev.document_filename}</div>
                      {ev.excerpt && (
                        <div className="text-xs text-slate-500 font-mono mt-0.5 italic">
                          "{ev.excerpt.slice(0, 150)}{ev.excerpt.length > 150 ? '…' : ''}"
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Conflict */}
          {answer.has_conflicts && answer.conflict_note && (
            <div className="rounded-lg border border-red-500/30 bg-red-900/10 p-3">
              <div className="flex items-center gap-2 text-red-400 text-sm font-medium mb-1">
                <AlertTriangle size={14} />
                Conflicting Records Detected
              </div>
              <div className="text-xs text-red-300/80">{answer.conflict_note}</div>
            </div>
          )}

          {/* Missing info */}
          {answer.missing_information && (
            <div className="rounded-lg border border-yellow-500/30 bg-yellow-900/10 p-3">
              <div className="flex items-center gap-2 text-yellow-400 text-sm font-medium mb-1">
                <HelpCircle size={14} />
                Insufficient Information
              </div>
              <div className="text-xs text-yellow-300/80">{answer.missing_information}</div>
            </div>
          )}

          {/* Confidence */}
          <div className="flex items-center gap-2 pt-2 border-t border-slate-800/50">
            <ConfidenceBadge confidence={answer.confidence} />
          </div>
        </div>
      )}
    </div>
  )
}

