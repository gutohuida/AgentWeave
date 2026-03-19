import React from 'react'

interface IconProps {
  name: string
  size?: number
  fill?: 0 | 1
  weight?: number
  className?: string
  style?: React.CSSProperties
}

/** Thin wrapper for Material Symbols Rounded variable font */
export function Icon({ name, size = 24, fill = 0, weight = 400, className, style }: IconProps) {
  return (
    <span
      className={`material-symbols-rounded select-none leading-none${className ? ' ' + className : ''}`}
      style={{
        fontSize: size,
        fontVariationSettings: `'FILL' ${fill}, 'wght' ${weight}, 'GRAD' 0, 'opsz' ${size}`,
        ...style,
      }}
      aria-hidden="true"
    >
      {name}
    </span>
  )
}
