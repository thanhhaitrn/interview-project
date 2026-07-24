import { useState } from "react";
import { Tag } from "./ui";

export function TagInput({
  values,
  onChange,
  placeholder,
}: {
  values: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");

  function add() {
    const v = draft.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft("");
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {values.map((v, i) => (
          <Tag key={`${v}-${i}`} onRemove={() => onChange(values.filter((_, j) => j !== i))}>
            {v}
          </Tag>
        ))}
      </div>
      <div className="mt-2 flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder={placeholder}
          className="flex-1 rounded-xl border border-navy/15 px-4 py-2 text-sm"
        />
        <button
          onClick={add}
          className="rounded-xl px-4 py-2 text-sm font-medium text-brand-600 hover:bg-brand/5"
        >
          Add
        </button>
      </div>
    </div>
  );
}
