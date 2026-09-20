import { useId, type ReactNode } from "react";
import { Check } from "./icons";

/**
 * Form controls in the ui-core vocabulary. Each one renders the artboard's
 * markup (`.field`, `.inp`, `.seg`, `.radio`, `.chk`) around a native control,
 * so the at-rest pixels match the design and the keyboard reaches everything.
 */
export function Field({ label, help, error, children, id }: { label: string; help?: ReactNode; error?: string[]; children: ReactNode; id?: string }) {
  const errId = id ? `${id}-err` : undefined;
  return (
    <div className={`field${error?.length ? " invalid" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children}
      {error?.length ? (
        <span className="err" id={errId} role="alert">
          {error[0]}
        </span>
      ) : help ? (
        <div className="help">{help}</div>
      ) : null}
    </div>
  );
}

type TextProps = {
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  error?: string[];
  multiline?: boolean;
  type?: "text" | "date";
  autoFocus?: boolean;
  maxLength?: number;
};

export function TextInput({ id, value, onChange, placeholder, error, multiline, type = "text", autoFocus, maxLength }: TextProps) {
  const common = {
    id,
    className: "ctl",
    value,
    placeholder,
    "aria-invalid": !!error?.length || undefined,
    "aria-describedby": error?.length ? `${id}-err` : undefined,
    autoFocus,
    maxLength,
  };
  return (
    <div className={`inp${multiline ? " ta" : ""}`}>
      {multiline ? (
        <textarea {...common} rows={3} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input {...common} type={type} onChange={(e) => onChange(e.target.value)} />
      )}
    </div>
  );
}

export function NumberInput({
  id,
  value,
  onChange,
  error,
  min,
  max,
  step,
  suffix,
}: {
  id: string;
  value: number | "";
  onChange: (v: number | "") => void;
  error?: string[];
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
}) {
  return (
    <div className="inp" style={{ width: 180 }}>
      <input
        id={id}
        className="ctl"
        type="number"
        inputMode="decimal"
        value={value}
        min={min}
        max={max}
        step={step}
        aria-invalid={!!error?.length || undefined}
        aria-describedby={error?.length ? `${id}-err` : undefined}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      />
      {suffix && (
        <span className="muted" style={{ fontSize: 12 }}>
          {suffix}
        </span>
      )}
    </div>
  );
}

/** Segmented control: one of a few options. */
export function Seg<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          className={o.value === value ? "on" : ""}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** A card-style radio, as the tier ceiling and model need choices are drawn. */
export function RadioCard({
  name,
  value,
  checked,
  onChange,
  title,
  sub,
}: {
  name: string;
  value: string;
  checked: boolean;
  onChange: () => void;
  title: string;
  sub: string;
}) {
  return (
    <label className={`radio ${checked ? "on" : ""}`}>
      <input type="radio" name={name} value={value} checked={checked} onChange={onChange} />
      <span className="rd"></span>
      <div className="col" style={{ gap: "0" }}>
        <b style={{ fontSize: "13px" }}>{title}</b>
        <span className="muted" style={{ fontSize: "11.5px" }}>
          {sub}
        </span>
      </div>
    </label>
  );
}

/** A checkbox row: box, label, and a quiet note to the right. */
export function CheckRow({
  checked,
  onChange,
  label,
  note,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  note?: string;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="row" style={{ gap: "9px", fontSize: "13px" }}>
      <label className={`chk ${checked ? "on" : ""}`} htmlFor={id}>
        <input id={id} type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
        <span className="sr-only">{label}</span>
        {checked && <Check size={10} />}
      </label>
      <span>{label}</span>
      {note && (
        <span className="muted" style={{ fontSize: "12px" }}>
          {note}
        </span>
      )}
    </div>
  );
}
