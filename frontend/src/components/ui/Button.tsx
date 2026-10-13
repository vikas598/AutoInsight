// Button — the shared action control. Variants cover every button in the app
// so call sites never hand-assemble colour classes.

import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary:   "bg-primary text-white shadow-card hover:bg-primary-hover",
  secondary: "border border-line-strong bg-surface text-ink hover:bg-surface-sunken",
  ghost:     "text-ink-secondary hover:bg-surface-sunken hover:text-ink",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 gap-1.5 px-3 text-xs",
  md: "h-10 gap-2 px-4 text-sm",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: LucideIcon;
  children?: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon: Icon,
  className = "",
  type = "button",
  children,
  ...rest
}: Props) {
  return (
    <button
      type={type}
      className={`focus-ring inline-flex shrink-0 items-center justify-center rounded-control font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    >
      {Icon && <Icon className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} aria-hidden />}
      {children}
    </button>
  );
}
