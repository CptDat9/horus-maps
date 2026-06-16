
import { Loader2 } from 'lucide-react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'active';
  size?: 'xs' | 'sm' | 'md';
  loading?: boolean;
  icon?: React.ReactNode;
}

const V = {
  primary: 'bg-blue-600 hover:bg-blue-500 text-white border-transparent',
  secondary: 'bg-slate-700 hover:bg-slate-600 text-slate-100 border-slate-600',
  ghost: 'bg-transparent hover:bg-slate-700/70 text-slate-300 border-transparent',
  danger: 'bg-red-800 hover:bg-red-700 text-white border-transparent',
  active: 'bg-blue-900/50 hover:bg-blue-800/50 text-blue-300 border-blue-700/50',
};

const S = {
  xs: 'px-1.5 py-0.5 text-xs gap-1 rounded',
  sm: 'px-2.5 py-1.5 text-xs gap-1.5 rounded-md',
  md: 'px-3.5 py-2 text-sm gap-2 rounded-lg',
};

export function Button({
  variant = 'secondary',
  size = 'sm',
  loading,
  icon,
  children,
  className = '',
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center border font-medium transition-colors
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
        disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer
        ${V[variant]} ${S[size]} ${className}`}
    >
      {loading ? <Loader2 size={12} className="animate-spin shrink-0" /> : icon}
      {children}
    </button>
  );
}
