export const environment = {
  production: false,
  apiBaseUrl: 'http://localhost:8000/api',
  entra: {
    // Completar tras crear el app registration en Entra ID (ver
    // docs/decisiones/ o CLAUDE.md). Tenant ID y Client ID de un SPA no son
    // secretos (van embebidos en el bundle), pero no se hardcodean acá
    // hasta que exista un registro real — evita apuntar a un tenant de
    // ejemplo por error.
    tenantId: 'bf893b22-5a5a-4535-80df-e385e1fc983d',
    clientId: 'ef365230-c6c2-48cb-a186-b94bb0439613',
    redirectUri: 'http://localhost:4200',
    apiScope: 'api://ef365230-c6c2-48cb-a186-b94bb0439613/access_as_user',
  },
};
