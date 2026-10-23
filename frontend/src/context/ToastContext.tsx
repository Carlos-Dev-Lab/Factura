import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';

interface ToastAction {
  label: string;
  onClick: () => void;
}

type Show = (message: string, action?: ToastAction) => void;

const ToastContext = createContext<Show>(() => undefined);

const SHORT_MS = 2800;
// Con acción ("Deshacer") el aviso dura más: da tiempo a reaccionar.
const WITH_ACTION_MS = 7000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState('');
  const [action, setAction] = useState<ToastAction | undefined>();
  const [visible, setVisible] = useState(false);
  const timer = useRef<number>();

  const hide = useCallback(() => {
    setVisible(false);
    window.clearTimeout(timer.current);
  }, []);

  const show = useCallback<Show>((msg, act) => {
    setMessage(msg);
    setAction(act ? { ...act } : undefined);
    setVisible(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setVisible(false), act ? WITH_ACTION_MS : SHORT_MS);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className={`toast ${visible ? 'show' : ''} ${action ? 'has-action' : ''}`} role="status" aria-live="polite">
        <span>{message}</span>
        {action && visible && (
          <button
            type="button"
            className="toast-action"
            onClick={() => {
              hide();
              action.onClick();
            }}
          >
            {action.label}
          </button>
        )}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
