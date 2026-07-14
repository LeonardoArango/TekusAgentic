export const environment = {
  production: true,
  apiBaseUrl: '/api',
  entra: {
    tenantId: '', // se completa en despliegue — no es secreto, pero no se hardcodea aquí
    clientId: '',
    redirectUri: window.location.origin,
    apiScope: '', // ej. api://<client-id-backend>/access_as_user
  },
};
