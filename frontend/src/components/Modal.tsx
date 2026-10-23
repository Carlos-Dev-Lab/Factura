import { useEffect, useRef, type FormEvent, type ReactNode } from 'react';

import { Icon } from './Icon';

interface Props {
  title: string;
  onClose: () => void;
  onSubmit: () => void;
  children: ReactNode;
  footer: ReactNode;
  /** Diálogo ancho (tablas, como la importación de extractos). */
  wide?: boolean;
}

/** Diálogo modal nativo (<dialog>): gestiona foco, Escape y fondo de forma accesible. */
export function Modal({ title, onClose, onSubmit, children, footer, wide = false }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  // Solo cierra si el clic empezó Y terminó en el fondo. Si no, seleccionar texto en un
  // campo y soltar el mouse afuera cerraba el diálogo (y descartaba la factura analizada).
  const pressedOnBackdrop = useRef(false);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || dialog.open) return;
    dialog.showModal();
    // `autoFocus` de React corre antes de que el diálogo se abra y se pierde: el campo inicial se marca con data-autofocus.
    dialog.querySelector<HTMLElement>('[data-autofocus]')?.focus();
  }, []);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit();
  };

  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? 'wide' : ''}`}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onMouseDown={(e) => {
        pressedOnBackdrop.current = e.target === ref.current;
      }}
      onClick={(e) => {
        if (pressedOnBackdrop.current && e.target === ref.current) onClose();
        pressedOnBackdrop.current = false;
      }}
    >
      <form className="modal-card" onSubmit={submit}>
        <div className="mh">
          <h2>{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Cerrar">
            <Icon name="close" size={18} />
          </button>
        </div>
        {children}
        <div className="mf">{footer}</div>
      </form>
    </dialog>
  );
}
