import { Component, inject, signal } from '@angular/core';
import { AuthService } from '../core/auth/auth.service';
import { RagQa } from '../conversaciones/rag-qa/rag-qa';

interface NavItem {
  key: string;
  label: string;
}

interface Kpi {
  label: string;
  value: string;
  delta: string;
  positive: boolean;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [RagQa],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class Dashboard {
  protected readonly auth = inject(AuthService);
  protected readonly active = signal('conocimiento');

  protected readonly nav: NavItem[] = [
    { key: 'resumen', label: 'Resumen' },
    { key: 'conversaciones', label: 'Conversaciones' },
    { key: 'conocimiento', label: 'Base de conocimiento' },
    { key: 'configuracion', label: 'Configuración' },
    { key: 'reportes', label: 'Reportes' },
  ];

  // KPIs de muestra para el shell — se conectarán a datos reales (métricas
  // SMART de Fase 1) cuando estén instrumentadas.
  protected readonly kpis: Kpi[] = [
    { label: 'Conversaciones hoy', value: '128', delta: '+18 vs. ayer', positive: true },
    { label: 'Tasa de deflexión', value: '63%', delta: '+4 pts esta semana', positive: true },
    { label: 'Tickets abiertos', value: '33', delta: 'En Odoo Helpdesk', positive: false },
    { label: 'Base de conocimiento', value: '4.1k', delta: 'tickets + wiki indexados', positive: true },
  ];

  protected iniciales(nombre: string | undefined): string {
    if (!nombre) {
      return 'TK';
    }
    return nombre
      .split(' ')
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase() ?? '')
      .join('');
  }
}
