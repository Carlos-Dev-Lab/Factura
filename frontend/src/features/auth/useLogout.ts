import { useQueryClient } from '@tanstack/react-query';

import { authApi } from '../../api/endpoints';
import { forgetThisDevice } from '../../lib/pwa';

/** Cierra la sesión de este dispositivo o, con `everywhere`, la de todos (por ejemplo, si perdiste el celular). */
export function useLogout() {
  const qc = useQueryClient();
  return async (everywhere?: boolean) => {
    await forgetThisDevice(); // antes de salir: necesita la sesión para avisarle al servidor
    // Solo `true` explícito: si se usa como onClick={logout}, llega el evento del clic y no debe contar.
    await (everywhere === true ? authApi.logoutAll() : authApi.logout()).catch(() => undefined);
    qc.clear();
    window.location.assign('/ingresar'); // al ingreso, no a la portada
  };
}
