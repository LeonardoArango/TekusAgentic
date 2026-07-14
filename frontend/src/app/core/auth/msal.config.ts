import {
  IPublicClientApplication,
  InteractionType,
  LogLevel,
  PublicClientApplication,
} from '@azure/msal-browser';
import {
  MsalGuardConfiguration,
  MsalInterceptorConfiguration,
} from '@azure/msal-angular';
import { environment } from '../../../environments/environment';

/**
 * SSO Microsoft 365 / Entra ID (MSAL) — single-tenant, solo usuarios de Tekus.
 * No implementar login local ni siquiera "temporal" (ver CLAUDE.md, sección Seguridad).
 */
export function msalInstanceFactory(): IPublicClientApplication {
  return new PublicClientApplication({
    auth: {
      clientId: environment.entra.clientId,
      authority: `https://login.microsoftonline.com/${environment.entra.tenantId}`,
      redirectUri: environment.entra.redirectUri,
      postLogoutRedirectUri: environment.entra.redirectUri,
    },
    cache: {
      cacheLocation: 'localStorage',
    },
    system: {
      loggerOptions: {
        loggerCallback: () => {
          /* silencioso por defecto; activar en debugging puntual */
        },
        logLevel: LogLevel.Warning,
        piiLoggingEnabled: false,
      },
    },
  });
}

export function msalGuardConfigFactory(): MsalGuardConfiguration {
  return {
    interactionType: InteractionType.Redirect,
    authRequest: {
      scopes: environment.entra.apiScope ? [environment.entra.apiScope] : [],
    },
  };
}

export function msalInterceptorConfigFactory(): MsalInterceptorConfiguration {
  const protectedResourceMap = new Map<string, Array<string>>();
  if (environment.entra.apiScope) {
    // MsalInterceptor usa matching estricto por defecto: la clave debe
    // terminar en `/*` para que haga match con subrutas (`/api/platform/...`),
    // si no, la compara como ruta exacta y el interceptor no adjunta ningún
    // token — sin error visible, solo un log "no scopes for endpoint".
    protectedResourceMap.set(`${environment.apiBaseUrl}/*`, [environment.entra.apiScope]);
  }

  return {
    interactionType: InteractionType.Redirect,
    protectedResourceMap,
  };
}
