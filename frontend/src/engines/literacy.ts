import type { Evidence, LiteracyTopic } from "@/types";
import type { UserContext } from "@/data/context";
import { round } from "@/lib/format";
import { runHealthEngine } from "./health";
import { runSpendingEngine } from "./spending";
import { runCashOutEngine } from "./cashout";
import { runEmergencyPlanner } from "./emergency";

/**
 * Personalised Financial Literacy Engine
 * ---------------------------------------------------------------------------
 * Not a generic tip list. Each lesson is triggered by a *measured* signal in
 * this customer's own ledger, uses their own numbers in the explanation, and
 * ends with one check-for-understanding so the copilot can adapt.
 */

interface TopicSeed extends LiteracyTopic {
  trigger: (ctx: UserContext) => { active: boolean; signal: string; strength: number };
}

const TOPICS: TopicSeed[] = [
  {
    id: "cash_flow_gap",
    title: "What is a cash-flow gap?",
    titleBn: "ক্যাশ-ফ্লো গ্যাপ কী?",
    hook: "You notice your balance dropping near month-end. Here is why that is a structural pattern, not bad luck.",
    hookBn:
      "মাস শেষের দিকে ব্যালেন্স কমে যাওয়ার কারণ দেখে নিন। এটি অদ্ভুত নয়, এটি একটি নিয়মিত প্যাটার্ন।",
    minutes: 1,
    triggerLabel: "Spending spikes late in the month",
    triggerLabelBn: "মাসের শেষ দিকে খরচ বেড়ে যাওয়া",
    relatedSignal: "end_month_shortage",
    trigger: (ctx) => {
      const late = ctx.monthly[ctx.monthly.length - 1]?.lateShare ?? 0;
      return {
        active: late > 0.32,
        signal: `last-10-days share of spending is ${(late * 100).toFixed(0)}%`,
        strength: Math.min(1, late / 0.5),
      };
    },
    sections: [
      {
        heading: "The idea",
        headingBn: "ধারণাটা",
        body:
          "A cash-flow gap appears when money leaves the account faster than it arrives, even though the monthly totals look acceptable. Income usually lands early in the month while commitments cluster later, so the running balance dips before the next income date.",
        bodyBn:
          "আয় সাধারণত মাসের শুরুতে আসে, কিন্তু ব্যয়গুলো পরে জমা হয়। ফলে মাসের মোট হিসাব মনে হওয়া মতো থাকলেও চলতি ব্যালেন্স পরবর্তী আয়ের আগেই নিচে নামে — এটিই ক্যাশ-ফ্লো গ্যাপ।",
      },
      {
        heading: "Why it matters",
        headingBn: "কেন গুরুত্বপূর্ণ",
        body:
          "A monthly total cannot warn you about a gap. The forecast engine therefore works day by day and places known commitments on their due dates, because that is the only way to see the trough.",
        bodyBn:
          "মাসের মোট যোগড়ি গ্যাপের ফোরকাস্ট করতে পারে না। তাই আমাদের ফোরকাস্ট ইঞ্জিন দিনে দিনে হিসাব করে এবং জানা দায়বদ্ধতাগুলো তার নির্ধারিত তারিখে বসায় — তখনই চলতি ব্যালেন্সের নিম্নমুখ ভাগ দেখা যায়।",
      },
      {
        heading: "What to do",
        headingBn: "কী করবেন",
        body:
          "Move one flexible commitment earlier, or shift a portion of late-month discretionary spending into the first half of the month. The simulator lets you test both without changing anything real.",
        bodyBn:
          "একটি নমনীয় দায় একটু আগে সরিয়ে নিন, অথবা মাসের শেষের ব্যয়ের একটি অংশ প্রথম অর্ধেতে সরান। সিমুলেটরে দুটোই পরীক্ষা করা যায়, আসল কিছু বদলানো ছাড়াই।",
      },
    ],
    quiz: {
      question: "Your monthly income and spending both look fine. What is still missing?",
      questionBn: "মাসের আয় ও ব্যয় দুটোই ঠিক আছে। তবুও কী অনুপস্থিত?",
      options: [
        { en: "Nothing — if the totals work, the month works", bn: "কিছু নয় — মোট হিসাব ঠিক থাকলে মাস ঠিক থাকবে" },
        { en: "The timing of income versus commitments", bn: "আয় ও দায়বদ্ধতার সময়ের ফারাক" },
        { en: "The number of transactions", bn: "লেনদেনের সংখ্যা" },
      ],
      answer: 1,
      explain:
        "A month can be solvent in total and still go cash-negative in the middle, purely because of timing.",
      explainBn: "মোট হিসাবে মাস ভালো থাকলেও শুধু সময়ক্রমের কারণে মাঝে ব্যালেন্স শূন্যের নিচে নামতে পারে।",
    },
  },
  {
    id: "emergency_fund",
    title: "What is an emergency fund?",
    titleBn: "জরুরি তহবিল কী?",
    hook: "Understand the buffer that keeps one bad month from turning into debt.",
    hookBn: "এমন একটি বাফার যা একটি খারাপ মাসকে ঋণে পরিণত হতে দেয় না — সেটির অর্থ বুঝুন।",
    minutes: 1,
    triggerLabel: "Liquid balance covers less than one month",
    triggerLabelBn: "তরল ব্যালেন্স এক মাসেরও কম দিয়ে আছে",
    relatedSignal: "low_buffer",
    trigger: (ctx) => {
      const plan = runEmergencyPlanner(ctx);
      return {
        active: plan.monthsOfCoverNow < 1.5,
        signal: `buffer covers ${plan.monthsOfCoverNow.toFixed(1)} months of essential spend`,
        strength: Math.min(1, 1.5 / Math.max(0.2, plan.monthsOfCoverNow)),
      };
    },
    sections: [
      {
        heading: "The idea",
        headingBn: "ধারণাটা",
        body:
          "An emergency fund is cash set aside only for surprises: medical costs, a repair, a lost month of income. It is not an investment and it is not your goal money.",
        bodyBn:
          "জরুরি তহবিল হলো কেবল অপ্রত্যাশিত পরিস্থিতির জন্য আলাদা রাখা টাকা — চিকিৎসা, মেরামত, বা আয় বন্ধ। এটি বিনিয়োগ নয় এবং লক্ষ্যের টাকাও নয়।",
      },
      {
        heading: "The convention",
        headingBn: "প্রচলিত নিয়ম",
        body:
          "A widely used planning convention is three months of essential expenses. It is a heuristic, not a law — a single-income household with family support may need less, a freelancer with volatile income usually needs more.",
        bodyBn:
          "প্রচলিত পরিকল্পনার নিয়ম অনুযায়ী প্রয়োজনীয় মাসিক খরচের তিন মাস রাখা হয়। এটি একটি আনুমানিক ধারণা, কঠিন আইন নয় — একক আয়ের পরিবারের কম লাগতে পারে, অনিয়মিত আয়ের ফ্রিল্যান্সারের বেশি লাগে।",
      },
      {
        heading: "What to do",
        headingBn: "কী করবেন",
        body:
          "Use the Emergency Fund planner and change the multiplier. Seeing the target move from three months to one month is often more motivating than any advice.",
        bodyBn:
          "জরুরি তহবিল পরিকল্পনায় গিয়ে গুণকটি বদলে দেখুন। তিন মাস থেকে এক মাসে লক্ষ্য নামতে দেখলে অনেকেই বেশি উৎসাহ পান।",
      },
    ],
    quiz: {
      question: "Where should emergency fund money live?",
      questionBn: "জরুরি তহবিলের টাকা কোথায় রাখা উচিত?",
      options: [
        { en: "Locked in a long-term investment", bn: "দীর্ঘমেয়াদি বিনিয়োগে আটকে" },
        { en: "Liquid and reachable within a day", bn: "তরল, একদিনের মধ্যে বের করা যায় এমন" },
        { en: "Spendable on a holiday", bn: "ছুটির ব্যয়ে ব্যবহারযোগ্য" },
      ],
      answer: 1,
      explain: "The value of the fund is entirely in its availability at the moment you need it.",
      explainBn: "এই তহবিলের মূল্য নির্ভর করে তা প্রয়োজনের সময় সত্যিই হাতে পৌঁছাবে কি না তার উপর।",
    },
  },
  {
    id: "cash_dependency",
    title: "Cash in, cash out, and what it costs you",
    titleBn: "নগদ বের করা এবং তার খরচ",
    hook: "See how much of your money leaves the digital system — and what that visibility costs.",
    hookBn: "দেখুন আপনার কতটা টাকা ডিজিটাল ব্যবস্থা থেকে বেরিয়ে যাচ্ছে, এবং সেই দৃশ্যমানতার জন্য কী খরচ হয়।",
    minutes: 1,
    triggerLabel: "A large share of spending settles in cash",
    triggerLabelBn: "বড় অংশের ব্যয় নগদে হয়",
    relatedSignal: "high_cash_dependency",
    trigger: (ctx) => {
      const cash = runCashOutEngine(ctx);
      return {
        active: cash.shareOfSpend > 0.3,
        signal: `${(cash.shareOfSpend * 100).toFixed(0)}% of spending settles in cash`,
        strength: Math.min(1, cash.shareOfSpend / 0.7),
      };
    },
    sections: [
      {
        heading: "The idea",
        headingBn: "ধারণাটা",
        body:
          "Cash is a perfectly valid choice. The cost is not the withdrawal — it is that once money is physical, it disappears from the record, so the forecast, the anomaly detector and the goal planner all stop seeing it.",
        bodyBn:
          "নগদ ব্যবহার সম্পূর্ণ বৈধ। ব্যয় নয়, সমস্যা হলো টাকা বাইরে গেলেই তা রেকর্ড থেকে হারিয়ে যায়, ফলে ফোরকাস্ট, অস্বাভাবিক শনাক্তকরণ ও লক্ষ্য পরিকল্পনা আর তা দেখতে পায় না।",
      },
      {
        heading: "The trade-off",
        headingBn: "ভারসাম্য",
        body:
          "Some expenses genuinely need cash. The useful question is which recurring ones do, and which are habit. The analyzer lists what your cash actually funds.",
        bodyBn:
          "কিছু ব্যয়ের জন্য সত্যিই নগদ দরকার। গুরুত্বপূর্ণ প্রশ্ন হলো কোনগুলো ছাড়া বাকিগুলো অভ্যাসে হয়ে গেছে। বিশ্লেষক আপনার নগদ আসলে কোগুলোতে যাচ্ছে তা দেখায়।",
      },
      {
        heading: "What to do",
        headingBn: "কী করবেন",
        body:
          "Decide which cash expenses are unavoidable, then move only the discretionary ones. Keeping a small cash float is fine; losing visibility over the whole month is what distorts the forecast.",
        bodyBn:
          "কোন নগদ ব্যয়গুলো অপরিহার্য তা ঠিক করে নিন, তারপর শুধু ইচ্ছাধীনগুলো সরান। অল্প নগদ রাখা ঠিক আছে; পুরো মাসের হিসাব অন্ধকারে থাকলেই ফোরকাস্ট নষ্ট হয়।",
      },
    ],
    quiz: {
      question: "Why does cash-out matter for a financial copilot?",
      questionBn: "ফাইন্যান্সিয়াল কোপাইলটের জন্য নগদ বের করা কেন গুরুত্বপূর্ণ?",
      options: [
        { en: "Cash withdrawal charges are high", bn: "নগদ উত্তোলনের ফি বেশি" },
        { en: "It removes money from the record the forecast can see", bn: "এতে টাকা ফোরকাস্ট দেখতে পারে এমন রেকর্ড থেকে বেরিয়ে যায়" },
        { en: "It is not allowed for some accounts", bn: "কিছু অ্যাকাউন্টে এটি নিষিদ্ধ" },
      ],
      answer: 1,
      explain: "Visibility, not permission, is the thing at stake.",
      explainBn: "অনুমতি নয়, দৃশ্যমানতাই এখানে মূল বিষয়।",
    },
  },
  {
    id: "savings_rate",
    title: "Saving on a small income",
    titleBn: "কম আয়ে সঞ্চয়",
    hook: "Why a percentage-based target beats an absolute one, and how to pick yours.",
    hookBn: "নির্দিষ্ট টাকার লক্ষ্যের চেয়ে শতাংশভিত্তিক লক্ষ্য কেন ভালো, এবং কীভাবে বেছে নেবেন।",
    minutes: 1,
    triggerLabel: "Savings rate is below 5%",
    triggerLabelBn: "সঞ্চয়ের হার ৫% এর নিচে",
    relatedSignal: "low_savings",
    trigger: (ctx) => {
      const health = runHealthEngine(ctx);
      const dim = health.dimensions.find((d) => d.key === "savings_behaviour");
      return {
        active: (dim?.value ?? 100) < 55,
        signal: `savings dimension at ${dim?.value ?? 0}/100`,
        strength: Math.min(1, (60 - (dim?.value ?? 60)) / 60),
      };
    },
    sections: [
      {
        heading: "The idea",
        headingBn: "ধারণাটা",
        body:
          "A percentage target survives a change in income. A fixed taka target quietly becomes impossible when the month gets shorter or the price of a bus ride goes up.",
        bodyBn:
          "শতাংশভিত্তিক লক্ষ্য আয় বদলালেও টিকে থাকে। নির্দিষ্ট টাকার লক্ষ্য আয় কমে গেলে বা খরচ বাড়লে ধীরে ধীরে অসম্ভব হয়ে পড়ে।",
      },
      {
        heading: "The ladder",
        headingBn: "ধাপ",
        body:
          "Save a percentage of income *after* income arrives, not of what is left. Writing it as a rule removes the monthly negotiation with yourself.",
        bodyBn:
          "আয় আসার পর আয়ের একটি শতাংশ সঞ্চয় করুন, বাকিটা থেকে নয়। এটি নিয়ম হিসেবে লিখে রাখলে প্রতি মাসে নিজের সঙ্গে দরকষাকষি বন্ধ হয়।",
      },
      {
        heading: "What to do",
        headingBn: "কী করবেন",
        body:
          "Open a goal in the planner at a rate you can sustain for three months. The optimiser will tell you honestly if the deadline is unrealistic.",
        bodyBn:
          "পরিকল্পনায় এমন একটি লক্ষ্য খুলুন যেটি তিন মাস ধরে চালিয়ে যেতে পারেন। অপটিমাইজার সৎভাবে জানিয়ে দেবে তারিখটি বাস্তবসম্মত কি না।",
      },
    ],
    quiz: {
      question: "Why prefer a percentage savings target?",
      questionBn: "শতাংশভিত্তিক সঞ্চয় লক্ষ্য কেন পছন্দ করবেন?",
      options: [
        { en: "It always produces more money", bn: "এতে সবসময় বেশি টাকা জমে" },
        { en: "It keeps working when income changes", bn: "আয় বদলালেও এটি কাজ করে" },
        { en: "Banks require it", bn: "ব্যাংক এটি চায়" },
      ],
      answer: 1,
      explain: "A rate keeps the habit intact through income changes; an absolute amount does not.",
      explainBn: "হার নির্ধারণ করলে আয় বদলালেও অভ্যাস থাকে; নির্দিষ্ট টাকার লক্ষ্যে তা ভেঙে যায়।",
    },
  },
  {
    id: "irregular_income",
    title: "Planning with irregular income",
    titleBn: "অনিয়মিত আয়ে পরিকল্পনা",
    hook: "How to plan when the amount and the date both move.",
    hookBn: "পরিমাণ ও তারিখ দুটোই বদলায় গেলে কীভাবে পরিকল্পনা করবেন।",
    minutes: 1,
    triggerLabel: "Income varies a lot month to month",
    triggerLabelBn: "মাসে আয় অনেক বদলায়",
    relatedSignal: "irregular_income",
    trigger: (ctx) => ({
      active: ctx.incomeCv > 0.3,
      signal: `income CV ${ctx.incomeCv.toFixed(2)}`,
      strength: Math.min(1, ctx.incomeCv),
    }),
    sections: [
      {
        heading: "The idea",
        headingBn: "ধারণাটা",
        body:
          "With irregular income, the average is a fiction — what matters is the *worst* month. Plan commitments against the lowest recent month, not the best one.",
        bodyBn:
          "অনিয়মিত আয়ে গড় মান আসলে কল্পনা — গুরুত্বপূর্ণ হলো সবচেয়ে খারাপ মাস। খরচের পরিকল্পনা সেরা মাসের নয়, সাম্প্রতিক সর্বনিম্ন মাসের ভিত্তিতে করুন।",
      },
      {
        heading: "The technique",
        headingBn: "কৌশল",
        body:
          "Smooth the flow: pay fixed commitments as soon as a payment lands, and treat a large payment as covering several months at once.",
        bodyBn:
          "আসতি সমান করুন: টাকা আসার সঙ্গে সঙ্গে নির্দিষ্ট দায়গুলো পরিশোধ করুন, আর বড় একটি আয়কে কয়েক মাসের জন্য একসঙ্গে হিসাবে নিন।",
      },
      {
        heading: "What to do",
        headingBn: "কী করবেন",
        body:
          "The forecast already widens its confidence band for irregular sources. Check the Money Sources page to see which part of your income is uncertain.",
        bodyBn:
          "ফোরকাস্ট ইঞ্জিন অনিয়মিত আয়ের জন্য নিজেই দ confidence ব্যান্ড চওড়া করে। কোন অংশটি অনিশ্চিত তা দেখতে মানি সোর্স পেজ দেখুন।",
      },
    ],
    quiz: {
      question: "With irregular income, which month should commitments be planned against?",
      questionBn: "অনিয়মিত আয়ে দায়বদ্ধতার পরিকল্পনা কোন মাসের ভিত্তিতে হবে?",
      options: [
        { en: "The best month", bn: "সেরা মাস" },
        { en: "The average month", bn: "গড় মাস" },
        { en: "The lowest recent month", bn: "সাম্প্রতিক সর্বনিম্ন মাস" },
      ],
      answer: 2,
      explain: "Commitments must survive the worst month, not the average one.",
      explainBn: "দায়বদ্ধতা সবচেয়ে খারাপ মাসেও পূরণ করতে হবে, গড় মাসে নয়।",
    },
  },
  {
    id: "interest_cost",
    title: "Why an instalment costs more than it looks",
    titleBn: "কিস্তির প্রকৃত খরচ",
    hook: "The price tag is not the total. Here is what borrowing cost really means.",
    hookBn: "লেবেলের দাম মোট খরচ নয়। আসলে ঋণের খরচ কেমন তা দেখুন।",
    minutes: 1,
    triggerLabel: "Recurring commitments already consume most of the surplus",
    triggerLabelBn: "নিয়মিত দায়বদ্ধতা ইতোমধ্যে বেশির ভাগ সঞ্চয় ব্যবহার করে",
    relatedSignal: "obligation_pressure",
    trigger: (ctx) => {
      const surplus = ctx.monthlyIncomeAvg - ctx.monthlySpendAvg;
      const obligations = ctx.recurring.reduce((a, r) => a + r.amount, 0);
      const pressure = surplus > 0 ? obligations / surplus : 1;
      return {
        active: pressure > 0.6,
        signal: `recurring commitments equal ${(pressure * 100).toFixed(0)}% of monthly surplus`,
        strength: Math.min(1, pressure / 2),
      };
    },
    sections: [
      {
        heading: "The idea",
        headingBn: "ধারণাটা",
        body:
          "An instalment of ৳3,000 for 12 months is not ৳36,000 — once interest is added it is more, and it occupies the same ৳3,000 every month whether or not you need it.",
        bodyBn:
          "১২ মাসে মাসে ৳৩,০০০ কিস্তি মোট ৳৩৬,০০০ নয় — সুদ যোগ হলে তা বেশি, আর প্রতিটি মাসে একই ৳৩,০০০ জায়গা নেয়, প্রয়োজন হোক বা না হোক।",
      },
      {
        heading: "The planning rule",
        headingBn: "পরিকল্পনার নিয়ম",
        body:
          "Size any instalment against your *surplus*, not your income. An instalment that fits inside surplus leaves the buffer intact; one that fits inside income does not.",
        bodyBn:
          "যেকোনো কিস্তির পরিমাণ আয়ের নয়, *সঞ্চয়ের* ভিত্তিতে ঠিক করুন। সঞ্চয়ের মধ্যে আসা কিস্তিই রিজার্ভ অক্ষত রাখে; আয়ের মধ্যে আসা কিস্তি রাখে না।",
      },
      {
        heading: "What to do",
        headingBn: "কী করবেন",
        body:
          "Use the hypothetical affordability calculator to see how a payment would sit against your surplus. It models nothing real and approves nothing.",
        bodyBn:
          "অনুমানমূলক অ্যাফোর্ডেবিলিটি ক্যালকুলেটরে দেখুন আপনার সঞ্চয়ের সঙ্গে কিস্তি কেমন বসে। এটি কিছুই অনুমোদন করে না, শুধু অনুমান করে।",
      },
    ],
    quiz: {
      question: "What should an instalment be sized against?",
      questionBn: "কিস্তির পরিমাণ কীসের ভিত্তিতে ঠিক করা উচিত?",
      options: [
        { en: "Monthly income", bn: "মাসিক আয়" },
        { en: "Monthly surplus", bn: "মাসিক সঞ্চয়" },
        { en: "Annual salary", bn: "বার্ষিক বেতন" },
      ],
      answer: 1,
      explain: "Surplus is what is actually free after essential spending.",
      explainBn: "প্রয়োজনীয় ব্যয়ের পর সত্যিই যা অবশিষ্ট, তাই সঞ্চয়।",
    },
  },
];

export interface LiteracyRecommendation {
  topic: LiteracyTopic;
  signal: string;
  strength: number;
  reason: string;
  reasonBn: string;
  evidence: Evidence;
}

export function runLiteracyEngine(ctx: UserContext): LiteracyRecommendation[] {
  const spending = runSpendingEngine(ctx);
  const out: LiteracyRecommendation[] = [];

  for (const seed of TOPICS) {
    const trigger = seed.trigger(ctx);
    if (!trigger.active) continue;
    out.push({
      topic: seed,
      signal: trigger.signal,
      strength: round(trigger.strength, 3),
      reason: `Triggered because ${trigger.signal}.`,
      reasonBn: `কারণ ${trigger.signal}।`,
      evidence: {
        engine: "Financial Literacy Personalizer",
        headline: seed.title,
        confidence: round(0.6 + trigger.strength * 0.25, 2),
        confidenceNote: "The lesson is selected by a measured signal, not by demographics.",
        metrics: [
          { id: "signal", label: "Triggering signal", value: seed.relatedSignal, unit: "text", detail: trigger.signal, source: "engine" },
          { id: "strength", label: "Signal strength", value: round(trigger.strength, 3), unit: "ratio", detail: "how strongly the pattern is present", source: "derived" },
        ],
        reasons: [
          { polarity: "neutral", text: `Discretionary spend this month is ৳${Math.round(spending.discretionarySpend).toLocaleString("en-US")} of ৳${Math.round(spending.totalSpend).toLocaleString("en-US")}.` },
        ],
        assumptions: [
          "Lessons are triggered by behaviour, never by age, gender or income level.",
          "Content uses the customer's own measured numbers rather than generic examples.",
        ],
        sources: ["engines: health, spending, cash-out, emergency"],
      },
    });
  }

  return out.sort((a, b) => b.strength - a.strength);
}

export function allTopics(): TopicSeed[] {
  return TOPICS;
}