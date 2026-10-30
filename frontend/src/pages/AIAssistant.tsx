import { useState, useEffect, useRef, useMemo } from 'react'
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
  History,
  Trash2,
  Plus,
  Search,
  Download,
  RotateCcw,
  MessageSquare,
} from 'lucide-react'
import { askAssistant, getAssistantSuggestions, type AssistantAnswer } from '@/lib/api'
import PageHeader from '@/components/PageHeader'
import { cn } from '@/lib/utils'

const CHAT_STORAGE_KEY = 'chronograph_assistant_chat_history_v2'

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
        'px-2.5 py-0.5 rounded-full text-[11px] font-medium border flex items-center gap-1.5',
        map[confidence] || map.Low
      )}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      Confidence: {confidence}
    </span>
  )
}

export interface MessageItem {
  id: string
  question: string
  answer: AssistantAnswer
  timestamp: string
  date: string
}

export default function AIAssistant() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialQuery = searchParams.get('q') || ''

  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<MessageItem[]>(() => {
    try {
      const saved = localStorage.getItem(CHAT_STORAGE_KEY)
      return saved ? JSON.parse(saved) : []
    } catch {
      return []
    }
  })

  const [historySearch, setHistorySearch] = useState('')
  const [activeMessageId, setActiveMessageId] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [expandedEvidence, setExpandedEvidence] = useState<Record<string, boolean>>({})

  const chatEndRef = useRef<HTMLDivElement>(null)
  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({})

  // Persist messages to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages))
    } catch (err) {
      console.warn('Could not save chat history to localStorage:', err)
    }
  }, [messages])

  const { data: suggestions } = useQuery({
    queryKey: ['suggestions'],
    queryFn: getAssistantSuggestions,
  })

  const askMutation = useMutation({
    mutationFn: (q: string) => askAssistant(q),
    onSuccess: (data, variables) => {
      const newItem: MessageItem = {
        id: `msg-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
        question: variables,
        answer: data,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        date: new Date().toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' }),
      }
      setMessages((prev) => [newItem, ...prev])
      setActiveMessageId(newItem.id)
      setQuestion('')
      if (initialQuery) {
        setSearchParams({})
      }
      setTimeout(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 150)
    },
  })

  // Trigger initial query from URL param if present
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

  const deleteMessage = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setMessages((prev) => prev.filter((m) => m.id !== id))
    if (activeMessageId === id) {
      setActiveMessageId(null)
    }
  }

  const clearAllHistory = () => {
    if (
      window.confirm(
        'Are you sure you want to clear your entire chat history? This cannot be undone.'
      )
    ) {
      setMessages([])
      setActiveMessageId(null)
      localStorage.removeItem(CHAT_STORAGE_KEY)
    }
  }

  const exportHistoryAsMarkdown = () => {
    if (messages.length === 0) return
    let md = `# ChronoGraph AI — Historical Q&A Export\nExported on: ${new Date().toLocaleString()}\n\n---\n\n`
    messages.forEach((m, idx) => {
      md += `### ${idx + 1}. ${m.question}\n`
      md += `*Asked on: ${m.date} at ${m.timestamp} | Confidence: ${m.answer.confidence}*\n\n`
      md += `${m.answer.answer}\n\n`
      if (m.answer.historical_events.length > 0) {
        md += `**Milestones:**\n`
        m.answer.historical_events.forEach((ev) => {
          md += `- **${ev.date}:** ${ev.description}\n`
        })
        md += `\n`
      }
      if (m.answer.supporting_evidence.length > 0) {
        md += `**Citations:**\n`
        m.answer.supporting_evidence.forEach((c) => {
          md += `- Source: \`${c.document_filename}\`\n  > "${c.excerpt || ''}"\n`
        })
        md += `\n`
      }
      md += `---\n\n`
    })

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `chronograph-chat-history-${Date.now()}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const scrollToMessage = (id: string) => {
    setActiveMessageId(id)
    const el = messageRefs.current[id]
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  // Filtered history for sidebar
  const filteredHistory = useMemo(() => {
    if (!historySearch.trim()) return messages
    const q = historySearch.toLowerCase()
    return messages.filter(
      (m) =>
        m.question.toLowerCase().includes(q) ||
        m.answer.answer.toLowerCase().includes(q)
    )
  }, [messages, historySearch])

  return (
    <div className="flex flex-col h-screen">
      {/* Top Header */}
      <div className="px-6 pt-5 pb-3 flex-shrink-0 border-b border-purple-900/20 bg-[#0a0f1e]/90 backdrop-blur-md">
        <PageHeader
          title="AI Historical Assistant"
          subtitle="Evidence-grounded chatbot with permanent chat history, multi-turn logging, and verifiable source citations"
          actions={
            <div className="flex items-center gap-2">
              {messages.length > 0 && (
                <>
                  <button
                    onClick={exportHistoryAsMarkdown}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 text-xs text-slate-300 border border-slate-700/50 transition-colors"
                    title="Export chat history as Markdown document"
                  >
                    <Download size={13} />
                    <span>Export Chat</span>
                  </button>
                  <button
                    onClick={clearAllHistory}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-950/30 hover:bg-red-900/50 text-xs text-red-300 border border-red-500/30 transition-colors"
                    title="Delete entire chat history"
                  >
                    <Trash2 size={13} />
                    <span>Clear History</span>
                  </button>
                </>
              )}
            </div>
          }
        />
      </div>

      {/* Main Two-Column Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel: Chat History Drawer */}
        <aside className="w-80 border-r border-purple-900/20 bg-[#0a0f24] flex flex-col flex-shrink-0">
          <div className="p-3 border-b border-purple-900/20 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-300">
                <History size={14} className="text-purple-400" />
                <span>Chat History ({messages.length})</span>
              </div>
              <button
                onClick={() => {
                  setActiveMessageId(null)
                  setQuestion('')
                }}
                className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md bg-purple-600/20 hover:bg-purple-600/40 text-purple-300 border border-purple-500/30 transition-colors"
                title="Start a new question"
              >
                <Plus size={12} />
                <span>New</span>
              </button>
            </div>

            {/* History Search input */}
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search past questions..."
                value={historySearch}
                onChange={(e) => setHistorySearch(e.target.value)}
                className="w-full bg-[#070b19] border border-slate-700/60 rounded-lg pl-8 pr-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-purple-500/70 transition-colors"
              />
            </div>
          </div>

          {/* History Item List */}
          <div className="flex-1 overflow-y-auto divide-y divide-slate-800/40 p-1.5">
            {messages.length === 0 ? (
              <div className="p-6 text-center text-slate-500 text-xs space-y-2">
                <MessageSquare size={28} className="mx-auto opacity-30 text-purple-400" />
                <div>No chat history yet.</div>
                <div className="text-[11px] text-slate-600">
                  Ask a question to start recording project intelligence.
                </div>
              </div>
            ) : filteredHistory.length === 0 ? (
              <div className="p-6 text-center text-slate-500 text-xs">
                No questions match "{historySearch}".
              </div>
            ) : (
              filteredHistory.map((m) => (
                <div
                  key={m.id}
                  onClick={() => scrollToMessage(m.id)}
                  className={cn(
                    'group p-2.5 rounded-lg text-left transition-all cursor-pointer relative mb-1',
                    activeMessageId === m.id
                      ? 'bg-purple-600/20 border border-purple-500/40 text-white'
                      : 'hover:bg-slate-800/50 text-slate-300 border border-transparent'
                  )}
                >
                  <div className="flex items-start justify-between gap-1.5">
                    <p className="text-xs font-medium leading-snug line-clamp-2 flex-1">
                      {m.question}
                    </p>
                    <button
                      onClick={(e) => deleteMessage(m.id, e)}
                      className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-400 rounded transition-opacity"
                      title="Delete this message"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                  <div className="flex items-center justify-between mt-2 text-[10px] text-slate-500 font-mono">
                    <span>{m.timestamp}</span>
                    <span
                      className={cn(
                        'px-1.5 py-0.2 rounded font-semibold',
                        m.answer.confidence === 'High'
                          ? 'text-emerald-400'
                          : m.answer.confidence === 'Medium'
                          ? 'text-yellow-400'
                          : 'text-orange-400'
                      )}
                    >
                      {m.answer.confidence}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* Right Panel: Conversation Stream & Input */}
        <div className="flex-1 flex flex-col overflow-hidden bg-[#070b19]">
          {/* Scrollable Conversation Stream */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-4xl w-full mx-auto">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto my-auto py-12 space-y-4">
                <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-purple-900/40">
                  <Bot size={24} className="text-white" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-white">
                    Temporal Intelligence Chatbot
                  </h3>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                    Ask questions regarding software features, architectural proposals, approvals,
                    or deprecations. All responses are 100% grounded in uploaded documents and
                    stored in your persistent chat history.
                  </p>
                </div>

                {/* Suggestions Grid */}
                {suggestions?.suggestions && (
                  <div className="w-full pt-2">
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">
                      Try asking:
                    </div>
                    <div className="grid grid-cols-1 gap-2 text-left">
                      {suggestions.suggestions.slice(0, 3).map((s, idx) => (
                        <button
                          key={idx}
                          onClick={() => {
                            setQuestion(s)
                            askMutation.mutate(s)
                          }}
                          className="p-3 rounded-xl bg-[#0d1530] hover:bg-purple-950/40 border border-purple-900/30 hover:border-purple-600/40 text-xs text-slate-300 hover:text-white transition-all flex items-center justify-between group"
                        >
                          <span className="truncate">{s}</span>
                          <Sparkles
                            size={13}
                            className="text-purple-400 opacity-60 group-hover:opacity-100 flex-shrink-0 ml-2"
                          />
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              messages.map((item) => {
                const ans = item.answer
                const isEvidenceOpen = expandedEvidence[item.id] ?? true
                const isActive = activeMessageId === item.id

                return (
                  <div
                    key={item.id}
                    ref={(el) => (messageRefs.current[item.id] = el)}
                    className={cn(
                      'rounded-2xl border bg-[#0d1530]/90 p-6 space-y-5 shadow-xl transition-all duration-200',
                      isActive
                        ? 'border-purple-500/60 shadow-purple-900/20'
                        : 'border-purple-900/30 hover:border-purple-500/30'
                    )}
                  >
                    {/* User Question Bubble */}
                    <div className="flex items-start justify-between gap-3 border-b border-slate-800/80 pb-4">
                      <div className="flex items-start gap-3">
                        <div className="p-2 rounded-xl bg-purple-600/20 text-purple-300 border border-purple-500/30 mt-0.5 flex-shrink-0">
                          <User size={16} />
                        </div>
                        <div>
                          <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">
                            Asked on {item.date} at {item.timestamp}
                          </div>
                          <h3 className="text-base text-white font-semibold mt-0.5 leading-snug">
                            {item.question}
                          </h3>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5 flex-shrink-0">
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
                        <button
                          onClick={(e) => deleteMessage(item.id, e)}
                          className="p-1.5 rounded-lg bg-slate-800/80 hover:bg-red-950/40 text-slate-400 hover:text-red-400 border border-slate-700/50 transition-colors"
                          title="Delete from chat history"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>

                    {/* Assistant Grounded Answer */}
                    <div className="flex items-start gap-3">
                      <div className="p-2 rounded-xl bg-emerald-600/20 text-emerald-300 border border-emerald-500/30 mt-0.5 flex-shrink-0">
                        <Bot size={16} />
                      </div>
                      <div className="flex-1 space-y-3">
                        <div className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap font-sans">
                          {ans.answer}
                        </div>

                        {/* Historical Milestones */}
                        {ans.historical_events.length > 0 && (
                          <div className="mt-4 pt-3 border-t border-slate-800/60">
                            <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                              Chronological Milestones
                            </div>
                            <div className="grid grid-cols-1 gap-2">
                              {ans.historical_events.map((e, idx) => (
                                <div
                                  key={idx}
                                  className="flex items-start gap-3 p-2.5 rounded-xl bg-slate-900/60 border border-slate-800/70 text-xs"
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
                                    className="p-3 rounded-xl bg-slate-900/70 border border-amber-500/20 text-xs space-y-1.5"
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

                        {/* Conflict Warning */}
                        {ans.has_conflicts && ans.conflict_note && (
                          <div className="rounded-xl border border-red-500/40 bg-red-950/20 p-3.5 space-y-1">
                            <div className="flex items-center gap-2 text-red-400 text-xs font-semibold uppercase tracking-wider">
                              <AlertTriangle size={14} />
                              Historical Conflict Recorded
                            </div>
                            <div className="text-xs text-red-200 leading-relaxed font-sans">
                              {ans.conflict_note}
                            </div>
                          </div>
                        )}

                        {/* Missing Information Notice */}
                        {ans.missing_information && (
                          <div className="rounded-xl border border-yellow-500/40 bg-yellow-950/20 p-3.5 space-y-1">
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

                    {/* Bottom Metadata Bar */}
                    <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-500">
                      <ConfidenceBadge confidence={ans.confidence} />
                      <button
                        onClick={() => {
                          setQuestion(item.question)
                          handleAsk()
                        }}
                        className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-purple-300 transition-colors"
                        title="Re-run query against latest records"
                      >
                        <RotateCcw size={11} />
                        <span>Re-verify</span>
                      </button>
                    </div>
                  </div>
                )
              })
            )}

            {/* In-flight loading animation */}
            {askMutation.isPending && (
              <div className="rounded-2xl border border-purple-500/30 bg-[#0d1530]/80 p-6 text-center text-slate-400 space-y-3 shadow-lg animate-pulse">
                <div className="flex items-center justify-center gap-2 text-purple-300 font-medium text-sm">
                  <Loader2 size={18} className="animate-spin text-purple-400" />
                  <span>Searching historical records and verifying evidence…</span>
                </div>
                <p className="text-xs text-slate-500 max-w-md mx-auto">
                  Extracting relevant chronological events, scoring keyword proximity, and validating
                  verbatim quotes.
                </p>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {/* Fixed Bottom Input Prompt */}
          <div className="p-4 border-t border-purple-900/20 bg-[#0a0f24]/90 backdrop-blur-md">
            <div className="max-w-4xl mx-auto space-y-2.5">
              <div className="flex gap-2.5">
                <div className="relative flex-1">
                  <textarea
                    className="w-full bg-[#070b19] border border-slate-700/60 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-500 resize-none focus:outline-none focus:border-purple-500/70 focus:ring-1 focus:ring-purple-500/40 transition-all font-sans leading-relaxed"
                    placeholder="Ask any historical question… (e.g., Why was Google authentication introduced?)"
                    rows={2}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={askMutation.isPending}
                  />
                </div>
                <button
                  className="px-5 py-3 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-medium text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50 self-end shadow-md shadow-purple-900/30 h-11"
                  onClick={handleAsk}
                  disabled={askMutation.isPending || !question.trim()}
                >
                  {askMutation.isPending ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Send size={16} />
                  )}
                  <span className="hidden sm:inline">Ask</span>
                </button>
              </div>

              {/* Suggestions row under prompt */}
              {suggestions?.suggestions && (
                <div className="flex items-center gap-1.5 overflow-x-auto py-1 text-xs no-scrollbar">
                  <span className="text-slate-400 font-medium text-[11px] flex-shrink-0 flex items-center gap-1">
                    <Sparkles size={11} className="text-purple-400" />
                    Suggested:
                  </span>
                  {suggestions.suggestions.slice(0, 4).map((s, i) => (
                    <button
                      key={i}
                      className="px-2.5 py-0.5 rounded-lg text-[11px] bg-slate-900/90 hover:bg-purple-950/40 text-slate-300 hover:text-purple-200 border border-slate-800 hover:border-purple-600/40 transition-all whitespace-nowrap flex-shrink-0"
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
          </div>
        </div>
      </div>
    </div>
  )
}
