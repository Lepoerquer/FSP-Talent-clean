import { useEffect } from 'react';

const BASE = 'ФСП Талант';

/** Заголовок вкладки браузера: помогает ориентироваться при нескольких вкладках и озвучивается программами экранного доступа. */
export const usePageTitle = (title?: string) => {
  useEffect(() => {
    document.title = title ? `${title} — ${BASE}` : `${BASE} — платформа подбора ИТ-специалистов`;
  }, [title]);
};
