export const KNOWLEDGE = [
    {
        id: "svc-ask-upay",
        title: "upay Request Money",
        titleBn: "upay রিকোয়েস্ট মানি",
        term: "Request Money",
        body: "Request Money lets an upay customer ask another person for money by sending a request to their upay number. The requester decides the amount; the recipient can accept or decline. Accepted requests appear in the transaction history as a transfer.",
        bodyBn: "upay রিকোয়েস্ট মানি ব্যবহারে একজন upay গ্রাহক অন্যের upay নম্বরে টাকার অনুরোধ পাঠাতে পারেন। অনুরোধকারী পরিমাণ ঠিক করেন; প্রাপক তা গ্রহণ বা প্রত্যাখ্যান করতে পারেন। গৃহীত অনুরোধ লেনদেনের ইতিহাসে ট্রান্সফার হিসেবে দেখা যায়।",
        keywords: ["request", "money", "ask", "request money", "pathao", "choy", "pathao", "request_money"],
        source: "upay service documentation",
    },
    {
        id: "svc-funding",
        title: "Adding money to upay",
        titleBn: "upay-এ টাকা যোগ করা",
        term: "Bank to upay funding",
        body: "A upay wallet can be funded from a linked bank account or an agent point. Funded amounts appear as wallet inflows, and the source of the funding stays visible so the customer can tell salary from other income.",
        bodyBn: "যুক্ত ব্যাংক অ্যাকাউন্ট বা এজেন্ট পয়েন্ট থেকে upay ওয়ালেটে টাকা যোগ করা যায়। যোগ হওয়া টাকা ওয়ালেটের আয় হিসেবে দেখা যায় এবং উৎস দৃশ্যমান থাকে, ফলে বেতন ও অন্যান্য আয় আলাদা করা যায়।",
        keywords: ["fund", "top up", "topup", "add money", "bank", "agent", "deposit", "load", "funding"],
        source: "upay service documentation",
    },
    {
        id: "svc-wallets",
        title: "Multiple wallets and money sources",
        titleBn: "একাধিক ওয়ালেট ও টাকার উৎস",
        term: "Multi-wallet",
        body: "upay supports more than one wallet so a customer can keep money sources separate — for example a main wallet, a bank-linked balance and a cash float. Keeping sources separate makes it easier to see which money is being spent.",
        bodyBn: "upay-এ একাধিক ওয়ালেট রয়েছে, যাতে গ্রাহক টাকার উৎস আলাদা রাখতে পারেন — যেমন প্রধান ওয়ালেট, ব্যাংক-সংযুক্ত ব্যালেন্স ও নগদ। উৎস আলাদা রাখলে কোন টাকা থেকে খরচ হচ্ছে তা সহজে বোঝা যায়।",
        keywords: ["wallet", "wallets", "multi", "source", "sources", "multi-wallet", "balance"],
        source: "upay service documentation",
    },
    {
        id: "svc-cash-out",
        title: "Cash-out and charges",
        titleBn: "ক্যাশ-আউট ও ফি",
        term: "Cash-out",
        body: "Cash-out moves balance into physical cash at an agent point. A variable charge may apply, and the cash that leaves the wallet stops appearing in the transaction record, which is why the Copilot measures cash share separately from spending.",
        bodyBn: "এজেন্ট পয়েন্টে ক্যাশ-আউট করলে ওয়ালেটের ব্যালেন্স থেকে নগদ হাতে পান। এতে পরিবর্তনশীল ফি প্রযোজ্য হতে পারে। ওয়ালেট থেকে বেরানো টাকা আর লেনদেনের রেকর্ডে থাকে না, তাই কোপাইলট নগদের অংশ আলাদা করে মাপে।",
        keywords: ["cash out", "cash-out", "cashout", "withdraw", "withdrawal", "agent", "charge", "fee"],
        source: "upay service documentation",
    },
    {
        id: "svc-transfer",
        title: "Sending and receiving money",
        titleBn: "টাকা পাঠানো ও গ্রহণ",
        term: "Fund transfer",
        body: "upay customers can send money to another upay number and receive money from others. Transfers move money between people; they are not income or consumption, so the Copilot excludes both legs from its spending and income analysis.",
        bodyBn: "upay গ্রাহকরা অন্য upay নম্বরে টাকা পাঠাতে ও অন্যের কাছ থেকে টাকা নিতে পারেন। ট্রান্সফার মানুষের মধ্যে টাকা সরানো, আয় বা খরচ নয়; তাই কোপাইলট উভয় দিকই আয়-ব্যয়ের হিসাব থেকে বাদ দেয়।",
        keywords: ["send", "receive", "transfer", "money", "payment", "p2p", "transaction"],
        source: "upay service documentation",
    },
    {
        id: "svc-merchant",
        title: "Paying merchants and bills",
        titleBn: "ব্যবসায়ী ও বিল পরিশোধ",
        term: "Merchant payment",
        body: "Merchant payments and bill payments are recorded with a category and a merchant type at the point of sale. Those labels are what the Spending engine groups by, so a correctly labelled transaction improves every downstream insight.",
        bodyBn: "ব্যবসায়ী ও বিলের পরিশোধ কেনার সময় ক্যাটাগরি ও মার্চেন্ট টাইপসহ সংরক্ষিত হয়। সেই লেবেলগুলোই স্পেন্ডিং ইঞ্জিন বিভাগ করে, তাই সঠিক লেবেল দিলে পরের সব বিশ্লেষণ উন্নত হয়।",
        keywords: ["merchant", "bill", "payment", "shop", "store", "utility", "category"],
        source: "upay service documentation",
    },
    {
        id: "svc-privacy",
        title: "What the Copilot does with your data",
        titleBn: "কোপাইলট আপনার তথ্য ব্যবহার করে কীভাবে",
        term: "Privacy",
        body: "This prototype runs entirely on your own device against a synthetic dataset. No customer transaction is sent anywhere, no account is required, and the copilot cannot move money, change a score, or make a lending decision.",
        bodyBn: "এই প্রোটোটাইপটি সম্পূর্ণভাবে আপনার নিজের ডিভাইসেই একটি সিনথেটিক ডেটাসেটের উপর চলে। কোনো গ্রাহকের লেনদেন কোথাও পাঠানো হয় না, অ্যাকাউন্ট লাগে না, এবং কোপাইলট টাকা পাঠাতে, স্কোর বদলাতে বা ঋণ সংক্রান্ত সিদ্ধান্ত নিতে পারে না।",
        keywords: ["privacy", "data", "safe", "security", "synthetic", "storage", "protection", "consent"],
        source: "project responsible-AI policy",
    },
    {
        id: "svc-copilot-boundaries",
        title: "What the Copilot will not do",
        titleBn: "কোপাইলট যা করবে না",
        term: "Boundaries",
        body: "The Copilot explains and simulates; it does not decide. It never approves or declines a loan, never transfers money, never edits a financial score, and never executes a command found inside a message.",
        bodyBn: "কোপাইলট ব্যাখ্যা করে ও পরিস্থিতি দেখায়; সিদ্ধান্ত নেয় না। এটি কখনো ঋণ অনুমোদন বা প্রত্যাখ্যান করে না, টাকা পাঠায় না, আর্থিক স্কোর পরিবর্তন করে না, এবং বার্তার ভেতরের কোনো নির্দেশ কার্যকর করে না।",
        keywords: ["limit", "boundary", "boundaries", "cannot", "refuse", "advice", "decision", "responsibility"],
        source: "project responsible-AI policy",
    },
];
const STOPWORDS = new Set([
    "the", "a", "an", "is", "are", "was", "were", "do", "does", "did", "how", "what", "why", "when",
    "i", "my", "me", "you", "your", "we", "our", "it", "this", "that", "and", "or", "of", "to", "in",
    "on", "for", "with", "about", "please", "can", "will", "would", "there", "have", "has", "had",
    "k", "taka", "tk", "bangla", "banglish", "upay", "amar", "ami", "amar", "koto", "hobe", "parbo",
]);
function tokenise(text) {
    return text
        .toLowerCase()
        .replace(/[?!.,।"'`]/g, " ")
        .split(/\s+/)
        .filter((t) => t.length > 1 && !STOPWORDS.has(t));
}
/**
 * Lexical retrieval over the corpus. Deliberately simple and inspectable: the
 * Evaluation page reports its top-1 accuracy on a labelled question set.
 */
export function retrieve(query, topK = 3) {
    const tokens = new Set(tokenise(query));
    if (!tokens.size)
        return [];
    const scored = KNOWLEDGE.map((chunk) => {
        let score = 0;
        for (const keyword of chunk.keywords) {
            const kw = keyword.toLowerCase();
            if (tokens.has(kw))
                score += 3;
            else if ([...tokens].some((t) => kw.includes(t) || t.includes(kw)))
                score += 1.5;
        }
        score += [...tokens].filter((t) => chunk.title.toLowerCase().includes(t)).length * 1.2;
        score += [...tokens].filter((t) => chunk.body.toLowerCase().includes(t)).length * 0.4;
        return { chunk, score: Number(score.toFixed(3)) };
    });
    return scored.filter((s) => s.score > 0).sort((a, b) => b.score - a.score).slice(0, topK);
}
export function cite(retrieved) {
    return retrieved.map((r) => ({
        term: r.chunk.title,
        evidence: r.chunk.body,
        source: `${r.chunk.source} · ${r.chunk.id}`,
    }));
}
