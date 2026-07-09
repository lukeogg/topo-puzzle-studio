export function SectionLabel({ label, chip }: { label: string; chip?: string }) {
  return (
    <div className="sectionLabel">
      <span className="lbl">{label}</span>
      {chip ? <span className="chip">{chip}</span> : null}
    </div>
  );
}
