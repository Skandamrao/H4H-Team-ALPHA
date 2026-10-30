import { useState } from 'react';
import QuestionBox from '../components/qa/QuestionBox';
import AnswerCard from '../components/qa/AnswerCard';
import type { QuestionAnswer } from '../types';

export default function QAPage() {
  const [answers, setAnswers] = useState<QuestionAnswer[]>([]);

  const handleAnswer = (a: QuestionAnswer) => {
    setAnswers(prev => [a, ...prev]);
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Ask Historical Questions</h1>
        <p className="text-sm text-gray-500 mt-1">
          Query the temporal knowledge base. Answers are grounded in retrieved events with verifiable source citations.
        </p>
      </div>

      <QuestionBox onAnswer={handleAnswer} />

      {answers.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
            Answers ({answers.length})
          </h2>
          {answers.map((a, i) => (
            <AnswerCard key={i} answer={a} />
          ))}
        </div>
      )}
    </div>
  );
}

