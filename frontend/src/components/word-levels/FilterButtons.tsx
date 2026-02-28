import type { CEFRLevel } from "@/lib/wordLevelsApi";

export type WordLevelFilter = "ALL" | "A2" | "B1" | "B2" | "C1" | "C2";

const FILTERS: WordLevelFilter[] = ["ALL", "A2", "B1", "B2", "C1", "C2"];

interface FilterButtonsProps {
  activeFilter: WordLevelFilter;
  onFilterChange: (filter: WordLevelFilter) => void;
  disabled?: boolean;
}

const ALLOWED_LEVELS: CEFRLevel[] = ["A2", "B1", "B2", "C1", "C2"];

export default function FilterButtons({ activeFilter, onFilterChange, disabled = false }: FilterButtonsProps) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Filter words by CEFR level">
      {FILTERS.map((filter) => {
        const isActive = activeFilter === filter;
        return (
          <button
            key={filter}
            type="button"
            disabled={disabled}
            aria-pressed={isActive}
            onClick={() => onFilterChange(filter)}
            className={`rounded-full border px-3 py-1.5 text-xs font-semibold tracking-wide transition-colors ${
              isActive
                ? "border-primary bg-primary/10 text-foreground"
                : "border-border bg-background text-muted-foreground hover:text-foreground"
            }`}
          >
            {filter}
          </button>
        );
      })}
      <span className="sr-only">
        Available level filters: {ALLOWED_LEVELS.join(", ")}
      </span>
    </div>
  );
}

