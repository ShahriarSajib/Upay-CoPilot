import type { Lang } from "@/types";

/**
 * UI copy for the shell and page chrome.
 *
 * Everything a customer reads on a screen comes from this dictionary or from an
 * engine's bilingual field pair. Keeping the chrome here means the language
 * switch is a single state change rather than a page-by-page audit.
 */

type Dict = Record<string, { en: string; bn: string }>;

export const UI: Dict = {
  appName: { en: "upay Financial Life Copilot", bn: "upay ফিন্যান্সিয়াল লাইফ কোপাইলট" },
  appTagline: {
    en: "Financial clarity, with the evidence attached",
    bn: "আর্থিক স্পষ্টতা, সঙ্গে তার প্রমাণ",
  },
  nav: { en: "Navigate", bn: "নেভিগেট" },
  groupOverview: { en: "Overview", bn: "সারসংক্ষেপ" },
  groupUnderstand: { en: "Understand", bn: "বোঝা" },
  groupPlan: { en: "Plan", bn: "পরিকল্পনা" },
  groupTrust: { en: "Trust & Safety", bn: "বিশ্বাস ও নিরাপত্তা" },

  dashboard: { en: "Dashboard", bn: "ড্যাশবোর্ড" },
  health: { en: "Financial Health", bn: "আর্থিক স্বাস্থ্য" },
  spending: { en: "Smart Spending", bn: "স্মার্ট খরচ" },
  forecast: { en: "Cash-Flow Forecast", bn: "ক্যাশ-ফ্লো পূর্বাভাস" },
  bills: { en: "Bills & Obligations", bn: "বিল ও দায়বদ্ধতা" },
  goals: { en: "Goals & Savings", bn: "লক্ষ্য ও সঞ্চয়" },
  simulator: { en: "What-If Simulator", bn: "হোয়াট-ইফ সিমুলেটর" },
  emergency: { en: "Emergency Fund", bn: "জরুরি তহবিল" },
  cashout: { en: "Cash-Out Intelligence", bn: "নগদ বিশ্লেষণ" },
  sources: { en: "Money Sources", bn: "উৎস বিশ্লেষণ" },
  resilience: { en: "Resilience", bn: "সহনশীলতা" },
  credit: { en: "Credit Readiness", bn: "ঋণ প্রস্তুতি" },
  literacy: { en: "Money Learning", bn: "অর্থ ব্যবস্থাপনা শিক্ষা" },
  review: { en: "Monthly Review", bn: "মাসিক পর্যালোচনা" },
  assistant: { en: "Ask upay", bn: "upay-কে জিজ্ঞাসা" },
  evaluation: { en: "Evaluation & Responsible AI", bn: "মূল্যায়ন ও দায়িত্বশীল AI" },

  evidence: { en: "Evidence", bn: "প্রমাণ" },
  showEvidence: { en: "Show evidence", bn: "প্রমাণ দেখুন" },
  confidence: { en: "Confidence", bn: "নির্ভরযোগ্যতা" },
  evidenceSources: { en: "Sources", bn: "উৎস" },
  assumptions: { en: "Assumptions", bn: "ধরণাবিধান" },
  reasons: { en: "Why", bn: "কেন" },
  metrics: { en: "Key numbers", bn: "মূল সংখ্যা" },
  forecast_shortage: { en: "Balance is projected to fall below the buffer", bn: "ব্যালেন্স রিজার্ভের নিচে নামার সম্ভাবনা" },
  methodology: { en: "How this is calculated", bn: "কীভাবে হিসাব হয়" },
  positives: { en: "Positives", bn: "শক্তিশালী দিক" },
  concerns: { en: "Concerns", bn: "উদ্বেগ" },

  language: { en: "Language", bn: "ভাষা" },
  english: { en: "English", bn: "ইংরেজি" },
  bangla: { en: "Bangla", bn: "বাংলা" },
  banglaNumerals: { en: "Bangla numerals", bn: "বাংলা সংখ্যা" },
  customer: { en: "Customer", bn: "গ্রাহক" },
  switchCustomer: { en: "Switch customer", bn: "গ্রাহক পরিবর্তন" },
  asOf: { en: "Ledger as of", bn: "লেজার তারিখ" },
  demoData: {
    en: "Synthetic demo cohort — no real customer data",
    bn: "সিনথেটিক ডেমো কোহর্ট — কোনো আসল গ্রাহকের তথ্য নয়",
  },
  loading: { en: "Loading financial context…", bn: "আর্থিক তথ্য প্রস্তুত হচ্ছে…" },
  loadError: { en: "The dataset could not be loaded.", bn: "ডেটা সেট লোড করা যায়নি।" },
  notReady: { en: "Waiting for the financial context engine…", bn: "ফিন্যান্সিয়াল কনটেক্সট ইঞ্জিনের জন্য অপেক্ষা করছে…" },
  back: { en: "Back", bn: "ফিরে যান" },
  thisMonth: { en: "This month", bn: "এই মাস" },
  lastMonth: { en: "Last month", bn: "গত মাস" },
  vsLastMonth: { en: "vs last month", bn: "গত মাসের তুলনায়" },
  today: { en: "today", bn: "আজ" },
  monthly: { en: "per month", bn: "প্রতি মাসে" },
  days: { en: "days", bn: "দিন" },
  months: { en: "months", bn: "মাস" },
  ofSpend: { en: "of spend", bn: "ব্যয়ের" },
  ofIncome: { en: "of income", bn: "আয়ের" },
  total: { en: "Total", bn: "মোট" },
  essential: { en: "Essential", bn: "প্রয়োজনীয়" },
  discretionary: { en: "Discretionary", bn: "সমন্বয়যোগ্য" },
  liquidBalance: { en: "Liquid balance", bn: "তরল ব্যালেন্স" },
  upayBalance: { en: "upay balance", bn: "upay ব্যালেন্স" },
  savingsRate: { en: "Savings rate", bn: "সঞ্চয়ের হার" },
  projected: { en: "Projected", bn: "প্রকৃতিপত" },
  baseline: { en: "Baseline", bn: "বেসলাইন" },
  scenario: { en: "Scenario", bn: "পরিস্থিতি" },
  model: { en: "Model", bn: "মডেল" },
  reset: { en: "Reset", bn: "রিসেট" },
  evaluate: { en: "What this means", bn: "এর অর্থ কী" },
  noData: { en: "Not enough history in this cohort to answer that.", bn: "এই কোহর্টে উত্তর দেওয়ার মতো যথেষ্ট ইতিহাস নেই।" },
  groundTruthNotice: {
    en: "Hatched rows use the generator's ground truth. They are shown for evaluation only and are never model inputs.",
    bn: "ডাঁকা লাইনগুলো জেনারেটরের গ্রাউন্ড ট্রুথ। এগুলো শুধু মূল্যায়নের জন্য, মডেলের ইনপুট নয়।",
  },
  askPlaceholder: {
    en: "Ask about your money — in English, বাংলা, or Banglish",
    bn: "আপনার টাকা নিয়ে জিজ্ঞাসা করুন — ইংরেজা, বাংলা বা বাংলিশে",
  },
  voiceUnsupported: {
    en: "Voice input is not available in this browser.",
    bn: "এই ব্রাউজারে ভয়েস ইনপুট চালু নেই।",
  },
};

export function t(key: string, lang: Lang): string {
  return UI[key]?.[lang] ?? UI[key]?.en ?? key;
}