export function Loading({ error }: { error?: Error | null }) {
  return (
    <div className="empty" role={error ? 'alert' : 'status'}>
      {error ? `No se pudo cargar: ${error.message}` : 'Cargando…'}
    </div>
  );
}
