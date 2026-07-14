import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface FuenteRag {
  page_title: string;
  page_url: string;
  space_key: string;
}

export interface RespuestaRag {
  puede_resolver: boolean;
  respuesta: string;
  fuentes: FuenteRag[];
}

/**
 * El interceptor de MSAL (ver core/auth/msal.config.ts) adjunta el Bearer
 * token automáticamente a cualquier request cuya URL empiece con
 * environment.apiBaseUrl — no hay que hacer nada especial acá para el SSO.
 */
@Injectable({ providedIn: 'root' })
export class RagQaService {
  private readonly http = inject(HttpClient);

  preguntar(pregunta: string): Observable<RespuestaRag> {
    return this.http.post<RespuestaRag>(`${environment.apiBaseUrl}/platform/rag/preguntas`, {
      pregunta,
    });
  }
}
