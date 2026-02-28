export default function WordLevelItem({ item }) {
  return (
    <li className="flex items-center justify-between rounded-xl border border-border bg-card px-4 py-3">
      <span className="text-sm font-medium text-foreground">{item.word}</span>
      <span className="rounded-full border border-border bg-muted px-3 py-1 text-xs font-semibold tracking-wide">
        {item.level}
      </span>
    </li>
  );
}

