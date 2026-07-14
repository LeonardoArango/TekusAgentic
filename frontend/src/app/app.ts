import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuthService } from './core/auth/auth.service';
import { RagQa } from './conversaciones/rag-qa/rag-qa';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RagQa],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly title = signal('Agente WhatsApp Tekus');

  constructor(protected readonly auth: AuthService) {}
}
