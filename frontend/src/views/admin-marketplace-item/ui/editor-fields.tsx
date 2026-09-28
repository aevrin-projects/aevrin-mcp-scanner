"use client";

import { useId, type ReactNode } from "react";

import { Input } from "@/shared/ui/input";
import { Textarea } from "@/shared/ui/textarea";

/**
 * Small form helpers for the item editor. Each one owns its label, so every
 * control is named for assistive technology without the caller wiring ids.
 */

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children(id)}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function TextField({
  label,
  hint,
  value,
  onChange,
  placeholder,
  type = "text",
  maxLength,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  maxLength?: number;
}) {
  return (
    <Field label={label} hint={hint}>
      {(id) => (
        <Input
          id={id}
          type={type}
          value={value}
          placeholder={placeholder}
          maxLength={maxLength}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </Field>
  );
}

export function LongTextField({
  label,
  hint,
  value,
  onChange,
  rows = 8,
  mono = false,
  placeholder,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  mono?: boolean;
  placeholder?: string;
}) {
  return (
    <Field label={label} hint={hint}>
      {(id) => (
        <Textarea
          id={id}
          rows={rows}
          value={value}
          placeholder={placeholder}
          className={mono ? "font-mono text-xs" : undefined}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </Field>
  );
}

/**
 * A list edited as text: one entry per line, or comma-separated for short
 * terms. The API normalises the terms; this only splits them.
 */
export function ListField({
  label,
  hint,
  values,
  onChange,
  separator = "comma",
}: {
  label: string;
  hint?: string;
  values: string[];
  onChange: (values: string[]) => void;
  separator?: "comma" | "line";
}) {
  const joined = values.join(separator === "comma" ? ", " : "\n");
  const split = (text: string) =>
    text
      .split(separator === "comma" ? /[,\n]/ : /\n/)
      .map((part) => part.trim())
      .filter(Boolean);
  return (
    <Field label={label} hint={hint}>
      {(id) =>
        separator === "comma" ? (
          <Input id={id} defaultValue={joined} onBlur={(event) => onChange(split(event.target.value))} />
        ) : (
          <Textarea id={id} rows={4} defaultValue={joined} onBlur={(event) => onChange(split(event.target.value))} />
        )
      }
    </Field>
  );
}
