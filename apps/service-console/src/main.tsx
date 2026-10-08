import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ServicePage } from './pages/ServicePage';
import './styles/base.css';

createRoot(document.getElementById('root')!).render(<StrictMode><ServicePage /></StrictMode>);
