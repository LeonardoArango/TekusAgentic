import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface FuenteRag {
  page_title: string;
  page_url: string;
  space_key: string;
}

export interface ChatResponse {
  conversation_id: string;
  tipo: 'pregunta' | 'respuesta' | 'escalar';
  texto: string;
  fuentes: FuenteRag[];
  intencion?: 'soporte' | 'venta' | 'mixto';
  fase?: string;
  ticket_ref?: string | null;
}

/**
 * El estado de la conversación vive en el servidor (Redis) por
 * conversation_id; el frontend solo manda el último mensaje + el id (que el
 * server devuelve en el primer turno). El interceptor de MSAL adjunta el
 * Bearer token automáticamente (ver core/auth/msal.config.ts).
 */
@Injectable({ providedIn: 'root' })
export class RagQaService {
  private readonly http = inject(HttpClient);

  chat(texto: string, conversationId: string | null): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(`${environment.apiBaseUrl}/platform/rag/chat`, {
      texto,
      conversation_id: conversationId,
    });
  }
}
