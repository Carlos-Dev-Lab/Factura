import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { ApiError } from './api/client';
import { App } from './App';
import { ToastProvider } from './context/ToastContext';
import { keys } from './hooks/queries';
import { registerServiceWorker } from './lib/pwa';
import '@fontsource-variable/manrope';
import '@fontsource-variable/sora';
import './styles/app.css';
import './styles/features.css';
import './styles/landing.css';
import './styles/auth.css';

// Si la sesión vence mientras se usa la app (al leer o al guardar), vuelve al inicio de sesión.
const onSessionError = (err: unknown) => {
  if (err instanceof ApiError && err.status === 401) queryClient.setQueryData(keys.me, null);
};

const queryClient: QueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
    },
  },
  queryCache: new QueryCache({ onError: onSessionError }),
  mutationCache: new MutationCache({ onError: onSessionError }),
});

registerServiceWorker();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <App />
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
