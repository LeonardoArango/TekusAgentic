import { Injectable, computed, signal } from '@angular/core';
import { MsalService } from '@azure/msal-angular';
import { AccountInfo } from '@azure/msal-browser';
import { environment } from '../../../environments/environment';

/**
 * Envoltorio delgado sobre MSAL. Toda la lógica real de auth vive en
 * @azure/msal-angular — este servicio solo expone el estado como signal
 * para el resto de la app.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly account = signal<AccountInfo | null>(null);
  readonly currentAccount = computed(() => this.account());
  readonly isAuthenticated = computed(() => this.account() !== null);

  constructor(private readonly msal: MsalService) {
    this.refreshAccount();
  }

  refreshAccount(): void {
    const accounts = this.msal.instance.getAllAccounts();
    this.account.set(accounts.length > 0 ? accounts[0] : null);
  }

  login(): void {
    // Pedimos el scope de nuestra API en el LOGIN, no después: así el
    // consentimiento se otorga de entrada y el interceptor puede sacar el
    // token de la API silenciosamente. Sin esto, la primera llamada al
    // backend falla con 400 (consent/interaction required) en el endpoint
    // de token de Microsoft.
    const scopes = environment.entra.apiScope ? [environment.entra.apiScope] : [];
    this.msal.loginRedirect({ scopes });
  }

  logout(): void {
    this.msal.logoutRedirect();
  }
}
