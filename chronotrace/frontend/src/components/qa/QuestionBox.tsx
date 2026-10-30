import { useState } from 'react';
import { Send, Loader } from 'lucide-react';
import type { QuestionAnswer } from '../../types';
import { askQuestion } from '../../api/client';
import { useAppStore } from '../../stores/useAppStore';

const EXAMPLE_QUESTIONS = [
  'When was OAuth2 Social Login implemented?',
  'Was Apple Sign-In ever approved?',
  'What was renamed and when?',
  'What features were implemented by February 2024?',
  'Which alternatives were rejected for the Search module?',
  'Is there anything that was proposed but never approved?',
];

interface QuestionBoxProps {
  onAnswer: (a: QuestionAnswer) => void;
}

export default function QuestionBox({ onAnswer }: QuestionBoxProps) {
  const { projectId } = useAppStore();
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (q: string) => {
    if (!q.trim()) return;
    setError(null);
    setLoading(true);
    try {
      const answer = await askQuestion({ question: q.trim(), project_id: projectId });
      onAnswer(answer);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'Query failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <input
          className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          placeholder="Ask about feature history, decisions, or changes…"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submit(question)}
          disabled={loading}
        />
        <button
          className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2"
          onClick={() => submit(question)}
          disabled={loading || !question.trim()}
        >
          {loading ? <Loader size={14} className="animate-spin" /> : <Send size={14} />}
          Ask
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex flex-wrap gap-2">
        {EXAMPLE_QUESTIONS.map((q, i) => (
          <button
            key={i}
            onClick={() => { setQuestion(q); submit(q); }}
            className="text-xs bg-gray-100 hover:bg-indigo-100 hover:text-indigo-800 text-gray-600 rounded-full px-3 py-1 border border-gray-200 transition-colors"
            disabled={loading}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

