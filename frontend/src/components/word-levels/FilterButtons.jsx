const FILTERS = ["ALL", "A2", "B1", "B2", "C1", "C2"];

export default function FilterButtons({ activeFilter, onFilterChange, disabled = false }) {
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
    </div>
  );
}

