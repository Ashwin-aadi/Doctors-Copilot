import { useId, useState } from "react";
import type { KeyboardEvent } from "react";
import { X } from "lucide-react";
import { cn } from "../../lib/cn";

export interface TagInputProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  suggestions?: string[];
  placeholder?: string;
}

export function TagInput({ label, values, onChange, suggestions = [], placeholder }: TagInputProps) {
  const [draft, setDraft] = useState("");
  const listId = useId();

  function addTag(raw: string) {
    const tag = raw.trim();
    if (!tag || values.includes(tag)) return;
    onChange([...values, tag]);
    setDraft("");
  }

  function removeTag(tag: string) {
    onChange(values.filter((v) => v !== tag));
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addTag(draft);
    } else if (e.key === "Backspace" && draft === "" && values.length > 0) {
      removeTag(values[values.length - 1]);
    }
  }

  const visibleSuggestions = suggestions.filter((s) => !values.includes(s));

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-fg">{label}</span>
      <div
        className={cn(
          "flex flex-wrap items-center gap-1.5 rounded-md border border-border bg-surface p-1.5",
        )}
      >
        {values.map((tag) => (
          <span
            key={tag}
            className="flex items-center gap-1 rounded-sm bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary"
          >
            {tag}
            <button
              type="button"
              aria-label={`Remove ${tag}`}
              onClick={() => removeTag(tag)}
              className="rounded-full hover:bg-primary/20"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          aria-label={label}
          list={listId}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => addTag(draft)}
          placeholder={values.length === 0 ? placeholder : undefined}
          className="min-w-[8rem] flex-1 bg-transparent px-1 py-1 text-sm text-fg outline-none placeholder:text-fg-subtle"
        />
        <datalist id={listId}>
          {visibleSuggestions.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </div>
    </div>
  );
}
