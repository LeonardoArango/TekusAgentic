import { Component, inject } from '@angular/core';
import { AuthService } from './core/auth/auth.service';
import { Login } from './login/login';
import { Dashboard } from './dashboard/dashboard';

@Component({
  selector: 'app-root',
  imports: [Login, Dashboard],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly auth = inject(AuthService);
}
