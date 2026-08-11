import type { ButtonHTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes } from 'react'

import './form.css'

interface FieldWrapperProps {
  label: string
  htmlFor: string
  hint?: string
}

function FieldLabel({ label, htmlFor, hint }: FieldWrapperProps) {
  return (
    <label className="form-field__label" htmlFor={htmlFor}>
      {label}
      {hint && <span className="form-field__hint"> — {hint}</span>}
    </label>
  )
}

type TextAreaFieldProps = FieldWrapperProps & TextareaHTMLAttributes<HTMLTextAreaElement>

export function TextAreaField({ label, htmlFor, hint, ...textareaProps }: TextAreaFieldProps) {
  return (
    <div className="form-field">
      <FieldLabel label={label} htmlFor={htmlFor} hint={hint} />
      <textarea id={htmlFor} className="form-field__textarea" rows={6} {...textareaProps} />
    </div>
  )
}

type TextFieldProps = FieldWrapperProps & InputHTMLAttributes<HTMLInputElement>

export function TextField({ label, htmlFor, hint, ...inputProps }: TextFieldProps) {
  return (
    <div className="form-field">
      <FieldLabel label={label} htmlFor={htmlFor} hint={hint} />
      <input id={htmlFor} className="form-field__input" {...inputProps} />
    </div>
  )
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'danger'
}

export function Button({ variant = 'primary', className, ...buttonProps }: ButtonProps) {
  const classes = ['button', `button--${variant}`, className].filter(Boolean).join(' ')
  return <button className={classes} {...buttonProps} />
}
