import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bot, Mic, MicOff, Send, ShieldAlert, Sparkles, Square, Volume2, VolumeX, Wrench, } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, PageHeader, cx } from "@/components/ui";
import { EvidenceBody } from "@/components/Evidence";
import { BENCHMARK, askCopilot, normaliseBanglish, } from "@/engines/assistant";
function speechRecognition() {
    if (typeof window === "undefined")
        return null;
    const w = window;
    return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}
function speechOut() {
    if (typeof window === "undefined")
        return null;
    return "speechSynthesis" in window ? window.speechSynthesis : null;
}
function pickVoice(synth, lang) {
    const voices = synth.getVoices();
    const prefix = lang === "bn" ? "bn" : "en";
    return (voices.find((v) => v.lang.toLowerCase().startsWith(prefix) && v.localService) ??
        voices.find((v) => v.lang.toLowerCase().startsWith(prefix)) ??
        null);
}
const STARTERS = [
    { en: "How much did I spend this month?", bn: "এই মাসে আমি কত টাকা খরচ করেছি?" },
    { en: "Why do I run short before month-end?", bn: "মাস শেষের আগে কেন টাকা কমে যায়?" },
    { en: "What will my balance be in 30 days?", bn: "৩০ দিনে আমার ব্যালেন্স কত হবে?" },
    { en: "Am I ready for credit?", bn: "আমি কি ঋণের জন্য প্রস্তুত?" },
    { en: "Ei mashe amar koto taka khoroch hoise?", bn: "এই মাসে আমার কত টাকা খরচ হয়েছে?" },
    { en: "Where does my money come from?", bn: "আমার টাকা কোথা থেকে আসে?" },
];
export default function Assistant() {
    const bundle = useBundle();
    const f = useFmt();
    const { lang, pushEvidence } = useCopilot();
    const [input, setInput] = useState("");
    const [turns, setTurns] = useState([]);
    const [listening, setListening] = useState(false);
    const [voiceError, setVoiceError] = useState(false);
    const [speakingId, setSpeakingId] = useState(null);
    const recognitionRef = useRef(null);
    const idRef = useRef(0);
    const Recognition = useMemo(() => speechRecognition(), []);
    const canSpeak = useMemo(() => speechOut() !== null, []);
    useEffect(() => {
        return () => {
            recognitionRef.current?.stop();
            recognitionRef.current = null;
            speechOut()?.cancel();
        };
    }, []);
    if (!bundle)
        return null;
    const stopSpeaking = () => {
        speechOut()?.cancel();
        setSpeakingId(null);
    };
    const speak = (turn) => {
        const synth = speechOut();
        if (!synth)
            return;
        if (speakingId === turn.id) {
            stopSpeaking();
            return;
        }
        synth.cancel();
        const utterance = new SpeechSynthesisUtterance(turn.answer.text);
        utterance.lang = turn.answer.lang === "bn" ? "bn-BD" : "en-US";
        const voice = pickVoice(synth, turn.answer.lang);
        if (voice)
            utterance.voice = voice;
        utterance.onend = () => setSpeakingId((id) => (id === turn.id ? null : id));
        utterance.onerror = () => setSpeakingId((id) => (id === turn.id ? null : id));
        setSpeakingId(turn.id);
        synth.speak(utterance);
    };
    const submit = (raw) => {
        const query = raw.trim();
        if (!query)
            return;
        stopSpeaking();
        const answer = askCopilot(bundle, query);
        idRef.current += 1;
        setTurns((prev) => [{ id: idRef.current, query, answer }, ...prev].slice(0, 12));
        setInput("");
    };
    const toggleVoice = () => {
        if (listening) {
            recognitionRef.current?.stop();
            setListening(false);
            return;
        }
        if (!Recognition) {
            setVoiceError(true);
            return;
        }
        const rec = new Recognition();
        rec.lang = lang === "bn" ? "bn-BD" : "en-US";
        rec.continuous = false;
        rec.interimResults = false;
        rec.onresult = (event) => {
            const text = Array.from({ length: event.results.length }, (_, i) => event.results[i][0].transcript)
                .join(" ")
                .trim();
            if (text) {
                setInput(text);
                submit(text);
            }
        };
        rec.onerror = () => {
            setVoiceError(true);
            setListening(false);
        };
        rec.onend = () => setListening(false);
        recognitionRef.current = rec;
        setVoiceError(false);
        setListening(true);
        try {
            rec.start();
        }
        catch {
            setVoiceError(true);
            setListening(false);
        }
    };
    return (_jsxs("div", { children: [_jsx(PageHeader, { title: copy("assistant", lang), subtitle: f.loc === "bn"
                    ? "ইংরেজি, বাংলা বা বাংলিশে জিজ্ঞাসা করুন। উত্তর আপনার লেজার থেকে হিসাব করা — কোনো অনুমান বা কোনো সাধারণ পরামর্শ নয়।"
                    : "Ask in English, বাংলা or Banglish. Every answer is calculated from your ledger — no guessing, no generic advice.", actions: _jsxs(Chip, { tone: "neutral", children: [_jsx(Wrench, { className: "h-3 w-3" }), f.loc === "bn" ? `${BENCHMARK.length} টি যাচাইকৃত প্রশ্ন` : `${BENCHMARK.length} verified questions`] }) }), _jsx("div", { className: "mb-5", children: _jsx(Banner, { tone: "warn", title: f.loc === "bn" ? "এই সহকারী যা করবে না" : "What this assistant will not do", icon: _jsx(ShieldAlert, { className: "h-4 w-4" }), children: _jsx("p", { children: f.loc === "bn"
                            ? "এটি আপনার স্কোর পরিবর্তন করতে পারে না, ঋণ অনুমোদন বা প্রত্যাখ্যান করতে পারে না, টাকা পাঠাতে পারে না, এবং ডেটাবেস বা কমান্ড চালাতে পারে না। প্রমাণ ছাড়া কোনো দাবি করা হয় না।"
                            : "It cannot change your scores, cannot approve or deny a loan, cannot move money, and cannot run database or shell commands. Nothing is asserted without the numbers behind it." }) }) }), _jsxs(Grid, { cols: 3, className: "mb-5", children: [_jsxs("div", { className: "col-span-2", children: [_jsx(Card, { children: _jsxs("div", { className: "flex flex-col gap-3", children: [_jsxs("div", { className: "flex flex-wrap items-end gap-2", children: [_jsxs("label", { className: "min-w-0 flex-1", children: [_jsx("span", { className: "mb-1.5 block text-[11px] font-semibold tracking-wide text-ink-400 uppercase", children: f.loc === "bn" ? "আপনার প্রশ্ন" : "Your question" }), _jsx("textarea", { value: input, onChange: (e) => setInput(e.target.value), onKeyDown: (e) => {
                                                                if (e.key === "Enter" && !e.shiftKey) {
                                                                    e.preventDefault();
                                                                    submit(input);
                                                                }
                                                            }, rows: 2, placeholder: copy("askPlaceholder", lang), className: "w-full resize-none rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-[13.5px] leading-relaxed text-ink-900 placeholder:text-ink-300" })] }), _jsxs("button", { type: "button", onClick: () => submit(input), className: "inline-flex h-[42px] items-center gap-1.5 rounded-xl bg-brand-500 px-4 text-[13px] font-bold text-white transition hover:bg-brand-600", children: [_jsx(Send, { className: "h-4 w-4" }), f.loc === "bn" ? "পাঠান" : "Ask"] }), _jsxs("button", { type: "button", onClick: toggleVoice, className: cx("inline-flex h-[42px] items-center gap-1.5 rounded-xl border px-3.5 text-[13px] font-bold transition", listening
                                                        ? "border-brand-500 bg-brand-500 text-white"
                                                        : "border-ink-200 bg-white text-ink-700 hover:border-brand-300"), children: [listening ? _jsx(Square, { className: "h-4 w-4" }) : _jsx(Mic, { className: "h-4 w-4" }), listening ? (f.loc === "bn" ? "শোনা হচ্ছে" : "Listening") : f.loc === "bn" ? "কথা বলুন" : "Speak"] })] }), voiceError || (!Recognition && !voiceError) ? (_jsxs("p", { className: "flex items-center gap-1.5 text-[11.5px] text-ink-500", children: [_jsx(MicOff, { className: "h-3.5 w-3.5" }), copy("voiceUnsupported", lang)] })) : null, _jsx("div", { className: "flex flex-wrap items-center gap-1.5 border-t border-ink-100 pt-3", children: STARTERS.map((s) => (_jsx("button", { type: "button", onClick: () => submit(f.loc === "bn" ? s.bn : s.en), className: "rounded-lg border border-ink-200 bg-ink-50/60 px-2.5 py-1.5 text-[11.5px] text-ink-700 transition hover:border-brand-300 hover:bg-brand-50", children: f.bi(s.en, s.bn) }, s.en))) })] }) }), turns.length ? (_jsx("div", { className: "mt-4 space-y-3", children: turns.map((turn) => (_jsxs(Card, { children: [_jsxs("div", { className: "flex items-start gap-2.5", children: [_jsx(Bot, { className: "mt-0.5 h-4 w-4 shrink-0 text-brand-500" }), _jsxs("div", { className: "min-w-0", children: [_jsx("p", { className: "text-[13px] leading-relaxed font-semibold text-ink-900", children: f.bi(turn.query, turn.query) }), turn.answer.normalised && turn.answer.normalised !== turn.query.toLowerCase() ? (_jsxs("p", { className: "mt-1 text-[10.5px] text-ink-400", children: [f.loc === "bn" ? "বোঝা হয়েছে:" : "interpreted as:", " ", turn.answer.normalised] })) : null] })] }), _jsx("div", { className: cx("mt-3 rounded-xl border px-3.5 py-3", turn.answer.blocked
                                                ? "border-brand-200 bg-brand-50/50"
                                                : "border-ink-200 bg-ink-50/40"), children: _jsx("p", { className: "text-[13.5px] leading-relaxed whitespace-pre-line text-ink-800", children: turn.answer.text }) }), _jsxs("div", { className: "mt-3 flex flex-wrap items-center gap-2", children: [_jsx(Chip, { tone: turn.answer.blocked ? "bad" : "neutral", children: turn.answer.blocked
                                                        ? f.loc === "bn" ? "প্রত্যাখ্যাত" : "refused"
                                                        : turn.answer.intentLabel }), _jsxs(Chip, { tone: "neutral", children: [f.loc === "bn" ? "আস্থা" : "confidence", " ", f.percent(turn.answer.confidence, 0)] }), _jsxs(Chip, { tone: "neutral", children: [f.loc === "bn" ? "ভাষা" : "lang", " ", turn.answer.lang === "bn" ? "বাংলা" : "English"] }), turn.answer.traces.length ? (_jsxs(Chip, { tone: "neutral", children: [_jsx(Wrench, { className: "h-3 w-3" }), turn.answer.traces.map((t) => t.tool).join(" → "), " \u00B7", " ", turn.answer.traces.reduce((a, t) => a + t.durationMs, 0), "ms"] })) : null, turn.answer.citations?.length ? (_jsxs(Chip, { tone: "brand", children: [f.loc === "bn" ? "সেবার তথ্য" : "service info", turn.answer.citations.length] })) : null, canSpeak ? (_jsxs("button", { type: "button", onClick: () => speak(turn), className: cx("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition", speakingId === turn.id
                                                        ? "border-brand-300 bg-brand-50 text-brand-800"
                                                        : "border-ink-200 bg-white text-ink-600 hover:border-brand-300 hover:text-brand-800"), "aria-label": speakingId === turn.id
                                                        ? f.loc === "bn" ? "উত্তর পড়া বন্ধ করুন" : "Stop reading"
                                                        : f.loc === "bn" ? "উত্তর পড়ে শোনান" : "Read answer aloud", children: [speakingId === turn.id ? (_jsx(VolumeX, { className: "h-3 w-3" })) : (_jsx(Volume2, { className: "h-3 w-3" })), speakingId === turn.id
                                                            ? f.loc === "bn" ? "থামান" : "Stop"
                                                            : f.loc === "bn" ? "শুনুন" : "Listen"] })) : null] }), turn.answer.evidence.map((e, i) => (_jsxs("details", { className: "mt-2 rounded-lg border border-ink-200 bg-white px-3 py-2", children: [_jsxs("summary", { className: "cursor-pointer text-[12px] font-bold text-ink-700", children: [copy("evidence", lang), ": ", e.headline] }), _jsx("div", { className: "mt-2", children: _jsx(EvidenceBody, { evidence: e }) })] }, i)))] }, turn.id))) })) : (_jsx("div", { className: "mt-4", children: _jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "শুরু করার আগে" : "Before you ask", title: f.loc === "bn" ? "কীভাবে কাজ করে" : "How this works" }), _jsx("ul", { className: "space-y-2 text-[12px] leading-relaxed text-ink-600", children: [
                                                {
                                                    en: "Your question is checked for scope first. Out-of-scope requests are refused before any tool runs.",
                                                    bn: "প্রথমে প্রশ্নের পরিধি যাচাই হয়। পরিধির বাইরের অনুরোধ কোনো টুল চালানোর আগেই প্রত্যাখ্যাত হয়।",
                                                },
                                                {
                                                    en: "An intent is detected from the wording, then a named engine runs on your ledger and returns figures.",
                                                    bn: "শব্দের ভিত্তিতে উদ্দেশ্য শনাক্ত হয়, তারপর নির্দিষ্ট ইঞ্জিন আপনার লেজারে হিসাব করে সংখ্যা দেয়।",
                                                },
                                                {
                                                    en: "Banglish input is normalised to a written form before matching, so typing without ঙ works.",
                                                    bn: "বাংলিশ লেখা লেখার আকারে রূপান্তরিত হয়, তাই ঙ ছাড়া লিখলেও কাজ করে।",
                                                },
                                                {
                                                    en: "Every answer carries the engine trace and evidence used to produce it.",
                                                    bn: "প্রতিটি উত্তরের সঙ্গে ইঞ্জিনের ট্রেস ও প্রয়োজনীয় প্রমাণ থাকে।",
                                                },
                                                {
                                                    en: "Speak your question, then press Listen to hear the answer read in your language.",
                                                    bn: "প্রশ্নটি বলুন, তারপর উত্তরটি আপনার ভাষায় শুনতে শুনুন চাপুন।",
                                                },
                                            ].map((line, i) => (_jsxs("li", { className: "flex items-start gap-2", children: [_jsx(Sparkles, { className: "mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-500" }), f.bi(line.en, line.bn)] }, i))) })] }) }))] }), _jsxs("div", { className: "space-y-4", children: [_jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "আজকের কনটেক্সট" : "Live context", title: f.loc === "bn" ? "যে তথ্য থেকে উত্তর আসে" : "What the answers are based on" }), _jsxs("ul", { className: "space-y-2 text-[12px] text-ink-600", children: [_jsxs("li", { className: "flex items-baseline justify-between gap-3 border-b border-ink-100 pb-1.5", children: [_jsx("span", { children: f.loc === "bn" ? "লেজার" : "Ledger as of" }), _jsx("span", { className: "tabular font-bold text-ink-800", children: f.shortDate(bundle.ctx.asOf.toISOString().slice(0, 10)) })] }), _jsxs("li", { className: "flex items-baseline justify-between gap-3 border-b border-ink-100 pb-1.5", children: [_jsx("span", { children: f.loc === "bn" ? "মাস" : "Months" }), _jsx("span", { className: "tabular font-bold text-ink-800", children: f.num(bundle.ctx.monthly.length) })] }), _jsxs("li", { className: "flex items-baseline justify-between gap-3 border-b border-ink-100 pb-1.5", children: [_jsx("span", { children: f.loc === "bn" ? "লেনদেন" : "Transactions" }), _jsx("span", { className: "tabular font-bold text-ink-800", children: f.num(bundle.ctx.transactions.length) })] }), _jsxs("li", { className: "flex items-baseline justify-between gap-3", children: [_jsx("span", { children: f.loc === "bn" ? "লক্ষ্য" : "Goals" }), _jsx("span", { className: "tabular font-bold text-ink-800", children: f.num(bundle.ctx.goals.length) })] })] }), _jsx("p", { className: "mt-3 text-[11px] leading-relaxed text-ink-400", children: f.loc === "bn"
                                            ? "সুবকারী কোনো বাইরের সেবা বা ওয়েব থেকে তথ্য নেয় না — শুধু এই কোহর্টের লেজার ও একটি স্থির সেবা-জ্ঞান ফাইল।"
                                            : "No external service or web call is made. Only this cohort's ledger and one fixed service-knowledge file are read." })] }), _jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "সীমাবদ্ধতা" : "Boundaries", title: f.loc === "bn" ? "যা এই সহকারী জানে না" : "What it does not know" }), _jsx("ul", { className: "space-y-1.5 text-[11.5px] leading-relaxed text-ink-600", children: [
                                            {
                                                en: "Real-time prices, exchange rates or interest-rate offers.",
                                                bn: "প্রত্যাশিত দাম, বিনিময় হার বা সুদের প্রস্তাব।",
                                            },
                                            {
                                                en: "Anything about another customer's data.",
                                                bn: "অন্য কোনো গ্রাহকের তথ্য।",
                                            },
                                            {
                                                en: "Whether a credit application would be approved anywhere.",
                                                bn: "কোথাও ঋণের আবেদন অনুমোদিত হতো কি না।",
                                            },
                                            {
                                                en: "Your bank account balance beyond what the ledger records.",
                                                bn: "লেজারে নেই এমন ব্যাংক ব্যালেন্স।",
                                            },
                                        ].map((line, i) => (_jsxs("li", { className: "flex items-start gap-2", children: [_jsx("span", { className: "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-300" }), f.bi(line.en, line.bn)] }, i))) })] }), _jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "বাংলিশ" : "Banglish", title: f.loc === "bn" ? "লেখার রূপান্তর" : "Normalisation" }), _jsx("p", { className: "text-[11.5px] leading-relaxed text-ink-600", children: f.loc === "bn"
                                            ? "আপনি যেভাবে লিখবেন, ইঞ্জিন সেটাকে লিখিত বাংলায় রূপান্তর করে নেয়। যেমন:"
                                            : "However you type, the engine normalises it to a written Bangla form before matching. For example:" }), _jsx("ul", { className: "mt-2 space-y-1", children: ["Ei mashe amar koto taka khoroch hoise?", "Ami ki 6 mash e 30 hazar joma korte parbo?", "Jodi proti mash e 1500 beshi jomi tahole ki hobe?"].map((q) => {
                                            const n = normaliseBanglish(q);
                                            return (_jsxs("li", { className: "rounded-lg bg-ink-50 px-2.5 py-1.5", children: [_jsx("p", { className: "text-[11.5px] text-ink-600", children: q }), _jsx("p", { className: "mt-0.5 text-[11.5px] font-semibold text-ink-800", children: n.normalised })] }, q));
                                        }) }), _jsx(Link, { to: "/evaluation", className: "mt-3 inline-block text-[12px] font-bold text-brand-700 hover:underline", children: f.loc === "bn" ? "যাচাইয়ের ফলাফল দেখুন" : "See measured accuracy" })] })] })] }), _jsx("div", { className: "mt-5", children: _jsxs(Banner, { tone: "neutral", title: f.loc === "bn" ? "উত্তরের দায়" : "Responsibility for the answer", children: [_jsx("p", { children: f.loc === "bn"
                                ? "সহকারী যা হিসাব করে তা দেখায় — সিদ্ধান্ত আপনার। কোনো উত্তরই আর্থিক পরামর্শ হিসেবে গণ্য হবে না।"
                                : "The assistant shows you the arithmetic. The decision stays yours. Nothing it says is financial advice." }), _jsx("button", { type: "button", onClick: () => pushEvidence(bundle.forecast30.evidence), className: "mt-2 text-[11.5px] font-bold text-brand-700 hover:underline", children: f.loc === "bn" ? "একটি উদাহরণ প্রমাণ দেখুন" : "See a sample evidence panel" })] }) })] }));
}
