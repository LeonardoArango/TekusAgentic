import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RagQaService, RespuestaRag } from './rag-qa.service';

@Component({
  selector: 'app-rag-qa',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './rag-qa.html',
  styleUrl: './rag-qa.scss',
})
export class RagQa {
  private readonly ragQa = inject(RagQaService);

  protected pregunta = '';
  protected readonly cargando = signal(false);
  protected readonly resultado = signal<RespuestaRag | null>(null);
  protected readonly error = signal<string | null>(null);

  preguntar(): void {
    const pregunta = this.pregunta.trim();
    if (!pregunta) {
      return;
    }

    this.cargando.set(true);
    this.error.set(null);
    this.resultado.set(null);

    this.ragQa.preguntar(pregunta).subscribe({
      next: (respuesta) => {
        this.resultado.set(respuesta);
        this.cargando.set(false);
      },
      error: () => {
        this.error.set('No se pudo obtener respuesta. Intenta de nuevo.');
        this.cargando.set(false);
      },
    });
  }
}
