import { Injectable, computed, signal } from '@angular/core';
import { MsalService } from '@azure/msal-angular';
import { AccountInfo } from '@azure/msal-browser';

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
    this.msal.loginRedirect();
  }

  logout(): void {
    this.msal.logoutRedirect();
  }
}
