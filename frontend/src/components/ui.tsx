import {
  Component,
  useEffect,
  useId,
  useRef,
  type ErrorInfo,
  type ReactNode,
} from "react";
import { AlertCircle, ArrowRight, Check, LoaderCircle, X } from "lucide-react";

export function Modal({
  title,
  eyebrow,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  eyebrow?: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const element = ref.current!;
    element.showModal();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      element.close();
      document.body.style.overflow = previous;
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? "wide" : ""}`}
      aria-labelledby={id}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          const r = e.currentTarget.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            onClose();
        }
      }}
    >
      <div className="modal-heading">
        <div>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h2 id={id}>{title}</h2>
        </div>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function ErrorBox({
  error,
  retry,
}: {
  error?: unknown;
  retry?: () => void;
}) {
  if (!error) return null;
  return (
    <div className="error-box" role="alert">
      <AlertCircle size={18} />
      <div>
        {error instanceof Error ? error.message : String(error)}
        {retry && (
          <button className="text-button" onClick={retry}>
            Try again <ArrowRight size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <span className="loading-label" role="status">
      <LoaderCircle size={18} className="spin" />
      {label}
    </span>
  );
}
export function Empty({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-symbol">{icon}</div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <span className={`badge ${tone}`}>
      <span className="badge-dot" />
      {children}
    </span>
  );
}
export function Toast({
  message,
  dismiss,
}: {
  message: string;
  dismiss: () => void;
}) {
  useEffect(() => {
    const id = window.setTimeout(dismiss, 5000);
    return () => clearTimeout(id);
  }, [message, dismiss]);
  return (
    <div className="toast" role="status">
      <span>
        <Check size={17} />
      </span>
      {message}
      <button
        className="icon-button"
        onClick={dismiss}
        aria-label="Dismiss notification"
      >
        <X size={16} />
      </button>
    </div>
  );
}
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    /* Do not log passenger details. */
  }
  render() {
    return this.state.error ? (
      <main className="fatal">
        <h1>Let’s get you back on track.</h1>
        <p>
          The page couldn’t load. Your saved bookings are still on the server.
        </p>
        <button
          className="button primary"
          onClick={() => window.location.reload()}
        >
          Reload website
        </button>
      </main>
    ) : (
      this.props.children
    );
  }
}
