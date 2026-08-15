import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "danger" | "subtle";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand-500 shadow-sm",
  ghost: "bg-transparent text-navy hover:bg-navy/5",
  subtle: "bg-white text-navy border border-navy/10 hover:bg-navy/5",
  danger: "bg-rose-500 text-white hover:bg-rose-600",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = "primary", className = "", ...rest }: ButtonProps) {
  return (
    <button
      className={`rounded-full px-5 py-2.5 text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...rest}
    />
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`card p-8 ${className}`}>{children}</div>;
}

export function Tag({
  children,
  onRemove,
}: {
  children: ReactNode;
  onRemove?: () => void;
}) {
  return (
    <span className="tag">
      {children}
      {onRemove && (
        <button
          onClick={onRemove}
          className="ml-1 text-brand-600/70 hover:text-brand-600"
          aria-label="Remove"
        >
          ×
        </button>
      )}
    </span>
  );
}

export function Badge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full bg-navy/5 px-3 py-1 text-xs font-medium text-navy/70">
      {children}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-navy/60">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand/30 border-t-brand" />
      {label}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <header className="mb-8">
      <h1 className="text-4xl font-extrabold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-2 text-navy/60">{subtitle}</p>}
    </header>
  );
}

export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { label: string; value: T }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-full border border-navy/10 bg-white p-0.5">
      {options.map((o) => (
        <button
          key={String(o.value)}
          onClick={() => onChange(o.value)}
          className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
            value === o.value ? "bg-brand text-white" : "text-navy/60 hover:bg-navy/5"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      {message}
    </div>
  );
}
