import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Icon } from './ui'

const compactStyle = { minHeight: 30, padding: '6px 10px', borderRadius: 6, background: '#112138', border: '1px solid #263a53', color: '#b7c6d8', boxShadow: 'none', fontSize: 10, fontWeight: 600 } as const

export function UiButton({ children, icon, className = '', style, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode; icon?: string }) {
  return <button {...props} className={`button compact-button ${className}`} style={{ ...compactStyle, ...style }}>{icon && <Icon name={icon} size={14}/>} {children}</button>
}
