import { cn } from "@/lib/utils";

const CEFR_CONFIG = {
  A1: { label: "A1 · Beginner", color: "bg-green-100 text-green-800 border-green-300 dark:bg-green-900/40 dark:text-green-300 dark:border-green-700" },
  A2: { label: "A2 · Elementary", color: "bg-green-100 text-green-800 border-green-400 dark:bg-green-900/40 dark:text-green-300 dark:border-green-600" },
  B1: { label: "B1 · Intermediate", color: "bg-yellow-100 text-yellow-800 border-yellow-400 dark:bg-yellow-900/40 dark:text-yellow-300 dark:border-yellow-700" },
  B2: { label: "B2 · Upper Inter.", color: "bg-orange-100 text-orange-800 border-orange-400 dark:bg-orange-900/40 dark:text-orange-300 dark:border-orange-700" },
  C1: { label: "C1 · Advanced", color: "bg-red-100 text-red-800 border-red-400 dark:bg-red-900/40 dark:text-red-300 dark:border-red-700" },
  C2: { label: "C2 · Mastery", color: "bg-red-200 text-red-900 border-red-500 dark:bg-red-900/50 dark:text-red-200 dark:border-red-600" },
};

export function getCefrColor(level) {
  return CEFR_CONFIG[level]?.color || CEFR_CONFIG.B1.color;
}

export function getCefrLabel(level) {
  return CEFR_CONFIG[level]?.label || level;
}

/**
 * Displays a coloured CEFR-level badge.
 *
 * @param {{ level: string, short?: boolean, className?: string }} props
 */
export default function CefrBadge({ level, short = false, className }) {
  const cfg = CEFR_CONFIG[level] || CEFR_CONFIG.B1;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        cfg.color,
        className,
      )}
      data-testid="cefr-badge"
    >
      {short ? level : cfg.label}
    </span>
  );
}
