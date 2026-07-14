import { Component, ElementRef, inject, signal, viewChild, effect } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { FuenteRag, MensajeChat, RagQaService } from './rag-qa.service';

interface TurnoUI {
  rol: 'user' | 'assistant';
  texto: string;
  fuentes?: FuenteRag[];
  tipo?: 'pregunta' | 'respuesta' | 'escalar';
}

@Component({
  selector: 'app-rag-qa',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './rag-qa.html',
  styleUrl: './rag-qa.scss',
})
export class RagQa {
  private readonly ragQa = inject(RagQaService);
  private readonly scroller = viewChild<ElementRef<HTMLDivElement>>('scroller');

  protected borrador = '';
  protected readonly cargando = signal(false);
  protected readonly turnos = signal<TurnoUI[]>([]);

  constructor() {
    // Auto-scroll al último turno cuando cambia la conversación.
    effect(() => {
      this.turnos();
      this.cargando();
      queueMicrotask(() => {
        const el = this.scroller()?.nativeElement;
        if (el) {
          el.scrollTop = el.scrollHeight;
        }
      });
    });
  }

  protected enviar(): void {
    const texto = this.borrador.trim();
    if (!texto || this.cargando()) {
      return;
    }

    this.turnos.update((t) => [...t, { rol: 'user', texto }]);
    this.borrador = '';
    this.cargando.set(true);

    const historial: MensajeChat[] = this.turnos().map((t) => ({ rol: t.rol, texto: t.texto }));

    this.ragQa.chat(historial).subscribe({
      next: (resp) => {
        this.turnos.update((t) => [
          ...t,
          {
            rol: 'assistant',
            texto: resp.texto,
            fuentes: resp.fuentes,
            tipo: resp.tipo,
          },
        ]);
        this.cargando.set(false);
      },
      error: () => {
        this.turnos.update((t) => [
          ...t,
          {
            rol: 'assistant',
            texto: 'Hubo un problema al procesar tu mensaje. Intenta de nuevo.',
          },
        ]);
        this.cargando.set(false);
      },
    });
  }

  protected reiniciar(): void {
    this.turnos.set([]);
    this.borrador = '';
  }
}
