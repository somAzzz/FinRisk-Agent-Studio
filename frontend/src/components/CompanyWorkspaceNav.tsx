type Section<K extends string> = { id: K; label: string };
export function CompanyWorkspaceNav<K extends string>({
  company,
  sections,
  active,
  onSelect,
  className = "company-tabs",
}: {
  company: string;
  sections: readonly Section<K>[];
  active: K;
  onSelect: (section: K) => void;
  className?: string;
}) {
  return (
    <nav className={className} aria-label={company + " workspace sections"}>
      {sections.map(({ id, label }) => (
        <button
          type="button"
          key={id}
          className={active === id ? "active" : undefined}
          aria-current={active === id ? "page" : undefined}
          onClick={() => onSelect(id)}
          data-testid={id === "supply-chain" ? "tab-supply-chain" : undefined}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
