// Ukrainian chrome strings for the Position Templates feature (T14).
//
// No i18n runtime yet — that mechanism is chosen in T20 (candidate session),
// which may move these into its message catalogue. Until then they live here
// as typed constants so the recruiter UI renders Ukrainian today (§11).
// Level names stay as the contract enum (Junior / Middle / Senior /
// Tech Leader); technical terms kept in English where a Ukrainian form is
// awkward.

export const positionsUk = {
  // List
  pageTitle: "Шаблони позицій",
  countActive: (n: number) => `${n} активних`,
  newCta: "+ Нова позиція",
  showArchived: "Показати архівовані",
  columns: {
    title: "Назва",
    level: "Рівень",
    stacks: "Стеки",
    competencies: "Компетенції",
    status: "Статус",
    actions: "Дії",
  },
  status: {
    active: "Активна",
    archived: "Архівована",
  },
  rowActions: {
    edit: "Редагувати",
    archive: "Архівувати",
  },

  // List states
  loadingLabel: "Завантаження позицій",
  empty: {
    heading: "Ще немає жодної позиції",
    prose: "Створіть перший шаблон позиції, щоб почати.",
  },
  error: {
    generic: "Не вдалося завантажити позиції.",
    retry: "Спробувати ще раз",
    unavailable: "Розділ позицій недоступний.", // 404 — feature off
    signIn: "Потрібен вхід.", // 401
    forbidden: "Недостатньо прав.", // 403
  },

  // Form
  form: {
    back: "← Назад до позицій",
    headingCreate: "Нова позиція",
    headingEdit: "Редагувати позицію",
    labels: {
      title: "Назва",
      level: "Рівень",
      jdText: "Опис вакансії",
      stacks: "Стеки",
      competencies: "Компетенції",
      mustHave: "Обовʼязкова",
    },
    levelPlaceholder: "Оберіть рівень",
    buttons: {
      cancel: "Скасувати",
      save: "Зберегти",
    },
    loadingLabel: "Завантаження форми",
    rubricError: "Не вдалося завантажити рубрику; створення недоступне.",
    notFound: "Позицію не знайдено.",
    validation: {
      titleRequired: "Вкажіть назву позиції.",
      titleTooLong: "Назва не може перевищувати 200 символів.",
      levelRequired: "Оберіть рівень.",
      stacksRequired: "Оберіть хоча б один стек.",
      competenciesRequired: "Оберіть хоча б одну компетенцію.",
      mustHaveSubset: "Обовʼязкові компетенції мають бути серед обраних.",
    },
  },

  // Archive confirm dialog
  archive: {
    title: "Архівувати позицію?",
    body: "Її буде приховано зі списку, але дані збережуться.",
    confirm: "Архівувати",
    cancel: "Скасувати",
  },
} as const;
