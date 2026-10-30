import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { format, parseISO, isValid } from 'date-fns'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return 'Unknown date'
  try {
    const date = parseISO(dateStr)
    if (!isValid(date)) return 'Unknown date'
    return format(date, 'MMM d, yyyy')
  } catch {
    return 'Unknown date'
  }
}

export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return 'Unknown'
  try {
    const date = parseISO(dateStr)
    if (!isValid(date)) return 'Unknown'
    return format(date, 'MMM d, yyyy HH:mm')
  } catch {
    return 'Unknown'
  }
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export const EVENT_TYPE_COLORS: Record<string, string> = {
  FEATURE_INTRODUCED: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  FEATURE_MODIFIED: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  FEATURE_RENAMED: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  FEATURE_REMOVED: 'bg-red-500/20 text-red-300 border-red-500/30',
  DECISION_PROPOSED: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  DECISION_APPROVED: 'bg-green-500/20 text-green-300 border-green-500/30',
  DECISION_REJECTED: 'bg-red-500/20 text-red-300 border-red-500/30',
  FEATURE_IMPLEMENTED: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  FEATURE_DEPRECATED: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  MODULE_CREATED: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30',
  MODULE_MODIFIED: 'bg-violet-500/20 text-violet-300 border-violet-500/30',
}

export const EVENT_TYPE_DOTS: Record<string, string> = {
  FEATURE_INTRODUCED: 'bg-emerald-400',
  FEATURE_MODIFIED: 'bg-blue-400',
  FEATURE_RENAMED: 'bg-cyan-400',
  FEATURE_REMOVED: 'bg-red-400',
  DECISION_PROPOSED: 'bg-yellow-400',
  DECISION_APPROVED: 'bg-green-400',
  DECISION_REJECTED: 'bg-red-500',
  FEATURE_IMPLEMENTED: 'bg-purple-400',
  FEATURE_DEPRECATED: 'bg-orange-400',
  MODULE_CREATED: 'bg-indigo-400',
  MODULE_MODIFIED: 'bg-violet-400',
}
