import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Icon } from './ui'

export function UiButton({ children, icon, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode; icon?: string }) {
  return <button {...props} className={`button compact-button ${className}`}>{icon && <Icon name={icon} size={14}/>} {children}</button>
}
