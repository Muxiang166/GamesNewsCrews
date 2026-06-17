/**
 * Shared workbench settings — SSR-safe via useState.
 *
 * Replaces provide/inject which can break across <NuxtPage>
 * boundaries during SSR hydration.
 */

const DEFAULTS = {
  apiBaseUrl: 'http://localhost:8000',
  dbPath: 'outputs/langgraph/mirror/games_news.db',
  themeSection: '',
  limit: 20,
};

export interface WorkbenchSettings {
  apiBaseUrl: string;
  dbPath: string;
  themeSection: string;
  limit: number;
}

function loadFromStorage(): WorkbenchSettings {
  if (import.meta.client) {
    try {
      const saved = localStorage.getItem('workbench-settings');
      if (saved) {
        return { ...DEFAULTS, ...JSON.parse(saved) };
      }
    } catch {
      // corrupted — use defaults
    }
  }
  return { ...DEFAULTS };
}

export const useSettings = () => {
  const settings = useState<WorkbenchSettings>('workbench-settings', () => loadFromStorage());

  const save = () => {
    if (import.meta.client) {
      localStorage.setItem('workbench-settings', JSON.stringify(settings.value));
    }
  };

  const reset = () => {
    settings.value = { ...DEFAULTS };
    if (import.meta.client) {
      localStorage.removeItem('workbench-settings');
    }
  };

  const getApiBase = () => {
    const runtime = useRuntimeConfig().public.apiBaseUrl;
    return (settings.value.apiBaseUrl || runtime || 'http://localhost:8000').replace(/\/+$/, '');
  };

  return { settings, save, reset, getApiBase };
};
