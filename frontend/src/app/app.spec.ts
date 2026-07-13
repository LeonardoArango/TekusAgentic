import { TestBed } from '@angular/core/testing';
import { PublicClientApplication } from '@azure/msal-browser';
import { MSAL_INSTANCE, MsalService, MsalBroadcastService } from '@azure/msal-angular';
import { Subject } from 'rxjs';
import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    const msalInstance = new PublicClientApplication({
      auth: { clientId: 'test-client-id' },
    });

    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        { provide: MSAL_INSTANCE, useValue: msalInstance },
        MsalService,
        {
          provide: MsalBroadcastService,
          useValue: { msalSubject$: new Subject(), inProgress$: new Subject() },
        },
      ],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('should render title', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.app-title')?.textContent).toContain('Agente WhatsApp Tekus');
  });
});
