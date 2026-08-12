export const STATUS_META = {
  pending: { label: 'Pending', dot: 'bg-slate-400', text: 'text-slate-300', badge: 'bg-slate-500/15 text-slate-300' },
  running: { label: 'Running', dot: 'bg-blue-400 animate-pulse', text: 'text-blue-300', badge: 'bg-blue-500/15 text-blue-300' },
  retrying: { label: 'Retrying', dot: 'bg-amber-400 animate-pulse', text: 'text-amber-300', badge: 'bg-amber-500/15 text-amber-300' },
  success: { label: 'Success', dot: 'bg-emerald-400', text: 'text-emerald-300', badge: 'bg-emerald-500/15 text-emerald-300' },
  failed: { label: 'Failed', dot: 'bg-red-400', text: 'text-red-300', badge: 'bg-red-500/15 text-red-300' },
  rolled_back: { label: 'Rolled back', dot: 'bg-orange-400', text: 'text-orange-300', badge: 'bg-orange-500/15 text-orange-300' },
  skipped: { label: 'Skipped', dot: 'bg-slate-500', text: 'text-slate-400', badge: 'bg-slate-500/15 text-slate-400' },
}

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.pending
}

export const TOOL_META = {
  notion: { label: 'Notion', emoji: '\u{1F4D3}' },
  google_drive: { label: 'Google Drive', emoji: '\u{1F4C2}' },
  teams: { label: 'Microsoft Teams', emoji: '\u{1F4AC}' },
  none: { label: 'Agent', emoji: '\u{1F916}' },
}
