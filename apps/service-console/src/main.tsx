import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ServicePage } from './pages/ServicePage';
import { LiveServicePage } from './pages/LiveServicePage';
import './styles/base.css';

createRoot(document.getElementById('root')!).render(<StrictMode>{window.location.pathname === '/service-preview' ? <ServicePage /> : <LiveServicePage />}</StrictMode>);
